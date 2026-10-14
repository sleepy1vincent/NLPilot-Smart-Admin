import { Component, ChangeDetectorRef, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';

interface ChatMessage {
  role: 'user' | 'ai';
  content: string;
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

    if (result?.need_confirm) {
      const ok = confirm(result.message || '确认执行此操作？');
      if (ok) {
        this._doConfirm(result.action, result.target, result?.data??"");
      } else {
        this._pushAi('已取消');
      }
      return;
    }

    const reply = this._formatReply(result, res?.message);
    this._pushAi(reply);
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

  private _pushAi(content: string): void {
    this.messages.push({ role: 'ai', content });
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

  private _formatReply(result: any, fallback: string): string {
  if (!result) return fallback ?? '（无回复）';

  const data = result.data;

  if (Array.isArray(data)) {
    if (data.length === 0) return '未找到数据';

    const lines = data.map((item: any) => {
      // 商品类（有 name + price）
      if (item.name != null && item.price != null) {
        const stock = item.stock != null ? `  库存 ${item.stock}` : '';
        return `· ${item.name}  ¥${item.price}${stock}`;
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