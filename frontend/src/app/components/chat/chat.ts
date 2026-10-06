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

    this.api.chat(text).subscribe({
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

    // 需要确认的操作（如删除）
    if (result?.need_confirm) {
      const ok = confirm(result.message || '确认执行此操作？');
      if (ok) {
        this._doConfirm(result.action, result.target);
      } else {
        this._pushAi('已取消');
      }
      return;
    }

    const reply = this._formatReply(result, res?.message);
    this._pushAi(reply);
  }

  private _doConfirm(action: string, target: string): void {
    this.api.confirm(action, target).subscribe({
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
    this._pushAi('请求失败：' + (err.error?.message || err.message));
  }

  private _formatReply(result: any, fallback: string): string {
    if (!result) return fallback ?? '（无回复）';

    const data = result.data;

    if (Array.isArray(data)) {
      if (data.length === 0) return '未找到匹配的商品';
      const lines = data.map((p: any) =>
        `· ${p.name}  ¥${p.price}  库存 ${p.stock}`
      );
      return `共 ${data.length} 条：\n${lines.join('\n')}`;
    }

    if (data && typeof data === 'object' && 'id' in data) {
      return `${result.message || '新增成功'}(ID: ${data.id})`;
    }

    // 对象含 affected = 修改/删除
    if (data && typeof data === 'object' && 'affected' in data) {
      return `${result.message || '操作成功'}（影响 ${data.affected} 行）`;
    }

    // 兜底
    return result.message ?? fallback ?? '（无回复）';
  }
}