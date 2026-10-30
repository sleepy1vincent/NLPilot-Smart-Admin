import { Component, ChangeDetectorRef, ElementRef, OnInit, ViewChild, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';

interface ChatMessage {
  role: 'user' | 'ai';
  content: string;
  /** result = 工具返回值（事实卡片）；reply = 文本气泡 */
  kind?: 'result' | 'reply';
  /** 结果来源：db = SQL 直查；rag = 语义召回 */
  source?: 'db' | 'rag';
  /** 多步循环的"总结" */
  summary?: boolean;
  /** 系统话术（clarify / refuse / 兜底），灰底居中 */
  system?: boolean;
  /** 卡片标题（多步时区分第几步、哪个工具） */
  label?: string;
}

/** 工具名 → 中文标签，用于卡片头部 */
const TOOL_LABEL: Record<string, string> = {
  query_products: '查询商品',
  recommend_products: '推荐商品',
  query_sales: '销售记录',
  sales_report: '销售统计',
  query_purchases: '进货记录',
  create_product: '新增商品',
  update_product: '修改商品',
  delete_product: '删除商品',
  apply_discount: '打折',
  record_sale: '记录销售',
  record_purchase: '记录进货',
};

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
export class Chat implements OnInit {
  messages: ChatMessage[] = [];
  conversations: ConvItem[] = [];
  conversationId: number | null = null;
  userInput = '';
  loading = false;

  @ViewChild('scroller') scroller?: ElementRef<HTMLElement>;

  private api = inject(ApiService);
  private cdr = inject(ChangeDetectorRef);

  ngOnInit(): void {
    this.refreshConversations();
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

  newChat(): void {
    this.conversationId = null;
    this.messages = [];
    this.userInput = '';
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
          kind: 'reply' as const,
        }));
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

  /** 欢迎页的快捷问题 */
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

    // 需要确认：工具只提了案，真正的写操作在 /api/chat/confirm
    if (result?.need_confirm) {
      const ok = confirm(result.message || '确认执行此操作？');
      if (ok) {
        this._doConfirm(result.action, result.target, result?.data ?? '');
      } else {
        this._pushAi('已取消', 'reply');
      }
      if (isNew) this.refreshConversations();
      return;
    }

    // 商品名没对上：反问，不执行
    if (result?.need_clarify) {
      this._pushAi(result.message || '你要找的是哪个商品？', 'reply');
      if (isNew) this.refreshConversations();
      return;
    }

    // 事实通道：真的调用了工具 → 渲染工具返回值
    // 多步时 data.results 里每一步都有一条，逐条渲染成卡片（以前只渲染最后一条，前面的数据会丢）
    if (data.executed) {
      const rows: any[] = Array.isArray(data.results) && data.results.length
        ? data.results
        : [{ step: 1, tool: (data.call || {}).tool, result }];

      const multi = rows.length > 1;
      for (const row of rows) {
        const r = row.result || {};
        const label = this._cardLabel(row.tool, row.step, multi);
        this._pushAi(this._formatResult(r, r.message), 'result',
                    r.is_rag ? 'rag' : 'db', false, false, label);
      }
      this.loading = false;

      // 多步循环的总结（单步模式 reply 为空，这里不会触发）
      const summary = (data.reply || '').trim();
      if (summary) this._pushAi(summary, 'reply', 'db', true);
      if (isNew) this.refreshConversations();
      return;
    }

    // 对话通道：clarify / refuse / 兜底 —— 全部是后端模板，不是模型原文
    this._pushAi(data.reply || res?.message || '（无回复）', 'reply', 'db', false, true);
    if (isNew) this.refreshConversations();
  }

  private _doConfirm(action: string, target: string, data: any): void {
    this.api.confirm(action, target, data).subscribe({
      next: (res: any) => this._pushAi(res?.message || '操作成功'),
      error: (err: any) =>
        this._pushAi('操作失败：' + (err.error?.message || err.message)),
    });
  }

  private _handleError(err: any): void {
    console.error('[chat] 请求失败:', err?.status, err?.message);
    let msg = '暂时无法处理，请稍后重试';
    if (err?.status === 0) msg = '网络连接失败，请检查后端是否启动（5001 端口）';
    else if (err?.status === 400) msg = err.error?.message || '输入格式不正确';
    else if (err?.status === 404) msg = '未找到相关数据';
    else if (err?.status >= 500) msg = '服务器暂时无法处理，请稍后重试';
    this._pushAi(msg);
  }

  // ---------------------------------------------------------------- 渲染

  private _pushAi(content: string, kind: 'result' | 'reply' = 'reply',
                  source: 'db' | 'rag' = 'db',
                  summary = false, system = false, label = ''): void {
    this.messages.push({ role: 'ai', content, kind, source, summary, system, label });
    this.loading = false;
    this.cdr.detectChanges();
    this._scrollToEnd();
  }

  /** 多步时卡片标题写成"第 2 步 · 查询商品"，单步时只写工具名 */
  private _cardLabel(tool: string, step: number, multi: boolean): string {
    const name = TOOL_LABEL[tool] || tool || '操作结果';
    return multi ? `第 ${step} 步 · ${name}` : name;
  }

  private _scrollToEnd(): void {
    setTimeout(() => {
      const el = this.scroller?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 30);
  }

  /** 只渲染"工具返回值"，绝不渲染模型的话 */
  private _formatResult(result: any, fallback: string): string {
    if (!result) return fallback ?? '（无回复）';

    const data = result.data;

    if (Array.isArray(data)) {
      if (data.length === 0) return result.message || '未找到数据';

      const lines = data.map((item: any) => {
        if (item.name != null && item.price != null) {
          const stock = item.stock != null ? `  库存 ${item.stock}` : '';
          const line = `· ${item.name}  ¥${item.price}${stock}`;
          return item.reason ? `${line}\n  理由：${item.reason}` : line;
        }
        if (item.product_name != null && item.quantity != null) {
          const amount = item.total != null ? `  ¥${item.total}` : '';
          const time = item.sold_at || item.purchased_at || '';
          const timeStr = time ? `  ${this._fmtTime(time)}` : '';
          return `· ${item.product_name}  × ${item.quantity}${amount}${timeStr}`;
        }
        return `· ${JSON.stringify(item)}`;
      });

      const head = result.message && !data.length ? result.message : `共 ${data.length} 条`;
      return `${head}：\n${lines.join('\n')}`;
    }

    if (data && typeof data === 'object' && 'id' in data) {
      return `${result.message || '新增成功'}（ID: ${data.id}）`;
    }
    if (data && typeof data === 'object' && 'affected' in data) {
      return `${result.message || '操作成功'}（影响 ${data.affected} 行）`;
    }

    return result.message ?? fallback ?? '（无回复）';
  }

  private _fmtTime(iso: string): string {
    if (!iso) return '';
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
}
