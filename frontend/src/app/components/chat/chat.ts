import { Component, ChangeDetectorRef, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';

interface ChatMessage {
  role: 'user' | 'ai';
  content: string;
  /** ai 消息的通道：result = 工具返回值（事实）；reply = 模型的话（对话） */
  kind?: 'result' | 'reply';
  /** 结果来源：db = SQL 直查；rag = 语义召回（向量检索） */
  source?: 'db' | 'rag';
  /** 这次请求走了几步（多步循环时有值） */
  steps?: number;
  /** 多步循环的"总结"：它是模型的话，但基于前面真实的工具结果 */
  summary?: boolean;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './chat.html',
  styleUrl: './chat.css',
})
export class Chat {
  messages: ChatMessage[] = [];
  userInput = '';
  loading = false;

  private api = inject(ApiService);
  private cdr = inject(ChangeDetectorRef);

  send(): void {
  const text = this.userInput.trim();
  if (!text || this.loading) return;

  this.messages.push({ role: 'user', content: text });
  this.userInput = '';
  this.loading = true;
  this.cdr.detectChanges();
  const history = this.messages
    .slice(-4)                                   
    .slice(0, -1)
    .map(m => ({
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.content,
    }));

    this.api.chat(text, history).subscribe({ 
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

  private _handleResponse(res: any): void {
    const result = res?.data?.result;

    // 需要用户确认：工具只提交了提案，真正的写操作在 /api/chat/confirm
    if (result?.need_confirm) {
      const ok = confirm(result.message || '确认执行此操作？');
      if (ok) {
        this._doConfirm(result.action, result.target, result?.data ?? '');
      } else {
        this._pushAi('已取消', 'reply');
      }
      return;
    }

    // 商品名没对上：反问用户，不执行操作
    if (result?.need_clarify) {
      this._pushAi(result.message || '你要找的是哪个商品？', 'reply');
      return;
    }

    // 事实通道：本次真的调用了工具 → 渲染工具返回的内容
    if (res?.data?.executed) {
      const source = result?.is_rag ? 'rag' : 'db';
      const steps = (res?.data?.trace || []).length;
      this._pushAi(this._formatResult(result, res?.message), 'result', source, steps);

      // 多步循环：卡片之后还有模型的"总结"，两个通道同时展示
      // （单步模式 reply 为空，这里不会触发）
      const summary = (res?.data?.reply || '').trim();
      if (summary) {
        this._pushAi(summary, 'reply', 'db', steps, true);
      }
      return;
    }

    // 对话通道：模型没有调用任何工具 → 本次没有任何数据库操作
    const reply = res?.data?.reply || res?.message || '（无回复）';
    this._pushAi(reply, 'reply');
  }

  private _doConfirm(action: string, target: string,data:any): void {
    this.api.confirm(action, target,data).subscribe({
      next: (res: any) => {
        this._pushAi(res?.message || '操作成功');
      },
      error: (err: any) => {
        this._pushAi('操作失败：' + (err.error?.message || err.message));
      },
    });
  }

  private _pushAi(content: string, kind: 'result' | 'reply' = 'reply',
                  source: 'db' | 'rag' = 'db', steps = 0, summary = false): void {
    this.messages.push({ role: 'ai', content, kind, source, steps, summary });
    this.loading = false;
    this.cdr.detectChanges();
  }

  private _handleError(err: any): void {
  console.error('[chat] 请求失败:', {
    status: err.status,
    statusText: err.statusText,
    error: err.error,
    message: err.message,
  });
  let userMessage = '抱歉，暂时无法处理，请稍后重试';
  if (err.status === 0) {
    userMessage = '网络连接失败，请检查网络后重试';
  } else if (err.status === 400) {
    userMessage = err.error?.message || '输入格式不正确';
  } else if (err.status === 404) {
    userMessage = '未找到相关数据';
  } else if (err.status === 500) {
    userMessage = '服务器暂时无法处理，请稍后重试';
  }
  this._pushAi(userMessage);
  this.loading = false;
  this.cdr.detectChanges();
}

  /** 只负责渲染"工具返回值"——绝不渲染模型的话 */
  private _formatResult(result: any, fallback: string): string {
  if (!result) return fallback ?? '（无回复）';

  const data = result.data;

  if (Array.isArray(data)) {
    if (data.length === 0) return result.message || '未找到数据';

    const lines = data.map((item: any) => {
      // 商品类（有 name + price）
      if (item.name != null && item.price != null) {
        const stock = item.stock != null ? `  库存 ${item.stock}` : '';
        const line = `· ${item.name}  ¥${item.price}${stock}`;
        // 推荐结果附带 reason（普通查询没有这个字段）
        return item.reason ? `${line}\n  理由：${item.reason}` : line;
      }

      // 销售/进货记录（有 product_name + quantity）
      if (item.product_name != null && item.quantity != null) {
        const amount = item.total != null ? `  ¥${item.total}` : '';
        const time = item.sold_at || item.purchased_at || '';
        const timeStr = time ? `  ${this._fmtTime(time)}` : '';
        return `· ${item.product_name}  × ${item.quantity}${amount}${timeStr}`;
      }

      // 兜底：JSON
      return `· ${JSON.stringify(item)}`;
    });

    return `共 ${data.length} 条：\n${lines.join('\n')}`;
  }

  // 对象含 id（新增）
  if (data && typeof data === 'object' && 'id' in data) {
    return `${result.message || '新增成功'}(ID: ${data.id})`;
  }

  // 对象含 affected（修改/删除）
  if (data && typeof data === 'object' && 'affected' in data) {
    return `${result.message || '操作成功'}（影响 ${data.affected} 行）`;
  }

  return result.message ?? fallback ?? '（无回复）';
}

private _fmtTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
}