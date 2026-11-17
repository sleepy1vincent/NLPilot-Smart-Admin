import {
  Component, ChangeDetectorRef, ElementRef, OnDestroy, OnInit, ViewChild, inject,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';

/** 对话区只放"话"：用户输入 + AI 的回复 / 模板话术 */
interface ChatMessage {
  role: 'user' | 'ai';
  content: string;
  /** 模板话术（clarify / refuse / 兜底）：虚线灰底 */
  system?: boolean;
  /** 多步总结 */
  summary?: boolean;
}

/** 右侧日志：AI 干了什么 */
interface LogEntry {
  time: string;
  level: 'INFO' | 'WARN' | 'ERROR';
  text: string;
  /** 可展开的原始数据 */
  detail?: string;
}

interface ConvItem {
  id: number;
  title: string;
  count: number;
  last_update: string;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './chat.html',
  styleUrl: './chat.css',
})
export class Chat implements OnInit, OnDestroy {
  messages: ChatMessage[] = [];
  logs: LogEntry[] = [];
  conversations: ConvItem[] = [];
  conversationId: number | null = null;
  userInput = '';
  loading = false;
  now = '';
  showConvs = false;
  expanded = new Set<number>();

  @ViewChild('scroller') scroller?: ElementRef<HTMLElement>;

  private api = inject(ApiService);
  private cdr = inject(ChangeDetectorRef);
  private timer: any;

  ngOnInit(): void {
    this.refreshConversations();
    this._tick();
    this.timer = setInterval(() => this._tick(), 1000);
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  private _tick(): void {
    const d = new Date();
    const p = (n: number) => String(n).padStart(2, '0');
    this.now = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} `
             + `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
    this.cdr.detectChanges();
  }

  // ---------------------------------------------------------------- 会话

  refreshConversations(): void {
    this.api.listConversations().subscribe({
      next: (res) => {
        this.conversations = res?.data ?? [];
        this.cdr.detectChanges();
      },
      error: () => (this.conversations = []),
    });
  }

  toggleConvs(): void {
    this.showConvs = !this.showConvs;
    this.cdr.detectChanges();
  }

  newChat(): void {
    this.conversationId = null;
    this.messages = [];
    this.logs = [];
    this.userInput = '';
    this.showConvs = false;
    this.cdr.detectChanges();
  }

  openChat(id: number): void {
    if (this.loading) return;
    this.api.getConversation(id).subscribe({
      next: (res) => {
        const rows = res?.data?.messages ?? [];
        this.conversationId = id;
        this.messages = rows.map((m: any) => ({
          role: m.role === 'user' ? 'user' : 'ai',
          content: m.content,
        }));
        // 历史日志：后端 action_logs 里存的每一步
        const rawLogs: any[] = res?.data?.logs ?? [];
        this.logs = rawLogs.map((a: any) => this._logFromRow(a)).reverse();
        if (!this.logs.length) {
          this.logs = [{
            time: this._hm(new Date()), level: 'INFO',
            text: `已载入历史会话 #${id}（${rows.length} 条消息，本次对话没有工具记录）`,
          }];
        }
        this.showConvs = false;
        this.cdr.detectChanges();
        this._scrollToEnd();
      },
    });
  }

  removeChat(ev: Event, id: number): void {
    ev.stopPropagation();
    if (!confirm('删除这个对话？')) return;
    this.api.deleteConversation(id).subscribe({
      next: () => {
        if (this.conversationId === id) this.newChat();
        this.refreshConversations();
      },
    });
  }

  // ---------------------------------------------------------------- 发送

  send(): void {
    const text = this.userInput.trim();
    if (!text || this.loading) return;

    this.messages.push({ role: 'user', content: text });
    this.userInput = '';
    this.loading = true;
    this.cdr.detectChanges();
    this._scrollToEnd();
    this._log('INFO', `收到指令：${text}`);

    this.api.chat(text, this.conversationId).subscribe({
      next: (res) => this._handleResponse(res),
      error: (err) => this._handleError(err),
    });
  }

  onKey(e: KeyboardEvent): void {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      this.send();
    }
  }

  quick(text: string): void {
    this.userInput = text;
    this.send();
  }

  // ---------------------------------------------------------------- 响应

  private _handleResponse(res: any): void {
    const data = res?.data ?? {};
    const result = data.result ?? {};
    const isNew = this.conversationId === null;
    if (data.conversation_id) this.conversationId = data.conversation_id;

    // 1) 写操作需要确认
    if (result?.need_confirm) {
      this._log('WARN', `${result.action}(${this._args({ target: result.target })}) 等待人工确认`);
      const ok = confirm(result.message || '确认执行此操作？');
      if (ok) {
        this._doConfirm(result.action, result.target, result?.data ?? '');
      } else {
        this._pushAi('已取消', true);
        this._log('INFO', '用户取消，未执行');
      }
      if (isNew) this.refreshConversations();
      return;
    }

    // 2) 商品名没对上：反问
    if (result?.need_clarify) {
      this._pushAi(result.message || '你要找的是哪个商品？', true);
      this._log('WARN', `未匹配到商品：${result.message || ''}`);
      if (isNew) this.refreshConversations();
      return;
    }

    // 3) 真的执行了工具：动作全部进右侧日志，对话区只放话
    const steps: any[] = Array.isArray(data.steps) ? data.steps : [];
    for (const s of steps) {
      if (!s) continue;
      const call = `${s.tool}(${this._args(s.args)})`;
      if (s.skipped) {
        this._log('WARN', `${call} 被跳过：${s.skipped}`);
      } else if (s.ok) {
        this._log('INFO', `${call} → ${this._summarize(s.result)}`,
                  s.result ? JSON.stringify(s.result) : undefined);
      } else {
        this._log('ERROR', `${call} → 执行失败`);
      }
    }

    const summary = (data.reply || '').trim();
    if (summary) {
      this._pushAi(summary, false, true);
      this._log('INFO', `模型自述：${summary.slice(0, 40)}`);
    } else if (data.executed) {
      this._log('INFO', `执行完毕，共 ${data.executed} 步`);
    }
    if (isNew) this.refreshConversations();
  }

  private _doConfirm(action: string, target: string, data: any): void {
    this._log('INFO', `确认执行 ${action}(${this._args({ target, data })})`);
    this.api.confirm(action, target, data, this.conversationId).subscribe({
      next: (res: any) => {
        this._pushAi(res?.message || '操作成功', true);
        this._log('INFO', `确认完成：${res?.message || '操作成功'}`);
      },
      error: (err: any) => {
        const msg = err.error?.message || err.message;
        this._pushAi('操作失败：' + msg, true);
        this._log('ERROR', `确认失败：${msg}`);
      },
    });
  }

  private _handleError(err: any): void {
    let msg = '暂时无法处理，请稍后重试';
    if (err?.status === 0) msg = '网络连接失败，请检查后端是否启动（5001 端口）';
    else if (err?.status === 400) msg = err.error?.message || '输入格式不正确';
    else if (err?.status === 404) msg = '未找到相关数据';
    else if (err?.status >= 500) msg = '服务器暂时无法处理，请稍后重试';
    this._pushAi(msg, true);
    this._log('ERROR', `请求失败：${msg}`);
  }

  // ---------------------------------------------------------------- 渲染

  private _pushAi(content: string, system = false, summary = false): void {
    this.messages.push({ role: 'ai', content, system, summary });
    this.loading = false;
    this.cdr.detectChanges();
    this._scrollToEnd();
  }

  private _log(level: LogEntry['level'], text: string, detail?: string): void {
    this.logs.unshift({ time: this._hm(new Date()), level, text, detail });
    if (this.logs.length > 300) this.logs.length = 300;
    this.cdr.detectChanges();
  }

  /** 把后端 action_logs 的一行还原成日志条目 */
  private _logFromRow(a: any): LogEntry {
    let args: any = a?.args;
    if (typeof args === 'string' && args) {
      try { args = JSON.parse(args); } catch { /* 保持原样 */ }
    }
    let detail: string | undefined = a?.detail || undefined;
    if (detail) {
      try { detail = JSON.stringify(JSON.parse(detail), null, 2); } catch { /* 保持原样 */ }
    }
    const call = `${a.tool}(${this._args(args)})`;
    const time = String(a.at || '').slice(11, 19) || this._hm(new Date());
    if (a.skipped) return { time, level: 'WARN', text: `${call} 被跳过：${a.skipped}` };
    if (a.ok === false) return { time, level: 'ERROR', text: `${call} → 执行失败` };
    return { time, level: 'INFO', text: `${call} → ${a.summary || 'ok'}`, detail };
  }

  private _hm(d: Date): string {
    const p = (n: number) => String(n).padStart(2, '0');
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }

  private _args(args: any): string {
    if (!args || (typeof args === 'object' && !Object.keys(args).length)) return '';
    let s = JSON.stringify(args);
    if (s.length > 72) s = s.slice(0, 72) + '…';
    return s;
  }

  /** 把工具返回值压成一行摘要 */
  private _summarize(r: any): string {
    if (!r) return '无返回';
    const d = r.data;
    if (Array.isArray(d)) {
      if (!d.length) return r.message || '0 条';
      const names = d.slice(0, 3)
        .map((x: any) => x?.name || x?.product_name || '')
        .filter(Boolean);
      return `${d.length} 条` + (names.length ? `：${names.join('、')}` : '');
    }
    if (d && typeof d === 'object') {
      if ('id' in d) return `新增 id=${d.id}`;
      if ('affected' in d) return `影响 ${d.affected} 行`;
    }
    return r.message || 'ok';
  }

  toggleDetail(i: number): void {
    if (this.expanded.has(i)) this.expanded.delete(i);
    else this.expanded.add(i);
    this.cdr.detectChanges();
  }

  private _scrollToEnd(): void {
    setTimeout(() => {
      const el = this.scroller?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 30);
  }
}
