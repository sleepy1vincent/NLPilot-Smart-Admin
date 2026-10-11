import { Component, OnInit, ChangeDetectorRef, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';
import { Product } from '../../models/product.model';

@Component({
  selector: 'app-product-list',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './product-list.html',
  styleUrl: './product-list.css',
})
export class ProductList implements OnInit {
  products: Product[] = []; 
  loading = false;
  errorMsg = '';
  newName = '';
  newPrice: number | null = null;
  newStock: number | null = null;
  yesterdaySoldMap: Record<string, number> = {};
  yesterdayBoughtMap: Record<string, number> = {};
  private api = inject(ApiService); 
  private cdr = inject(ChangeDetectorRef);

  ngOnInit(): void {
    this.load();
    this.loadYesterdaySold();
    this.loadYesterdayBought();
  }

  load(): void {
    this.loading = true;
    this.errorMsg = '';
    this.api.getProducts().subscribe({
      next: (res) => {
        this.products = res.data ?? [];
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.errorMsg = '加载失败：' + (err.error?.message || err.message);
        this.loading = false;
        this.cdr.detectChanges();
      },
    });
  }
  loadYesterdaySold(): void {
    this.api.getSales(undefined, 1).subscribe(res => {
    const rows = res.data ?? [];
    const map: Record<string, number> = {};
    for (const r of rows) {
      map[r.product_name] = (map[r.product_name] ?? 0) + r.quantity;
    }
    this.yesterdaySoldMap = map;
    this.cdr.detectChanges();
  });
  }
  loadYesterdayBought(): void {
    this.api.getBought(undefined, 1).subscribe(res => {
    const rows = res.data ?? [];
    const map: Record<string, number> = {};
    for (const r of rows) {
      map[r.product_name] = (map[r.product_name] ?? 0) + r.quantity;
    }
    this.yesterdayBoughtMap = map;
    this.cdr.detectChanges();
  });
  }
  editPrice(p: Product): void {
  const priceStr = prompt(`修改 ${p.name} 的价格（当前 ${p.price})`, p.price);
  if (priceStr == null) return;
  const price = parseFloat(priceStr);
  if (isNaN(price) || price < 0) {
    alert('价格不合法');
    return;
  }
  this.api.updateProduct(p.name, { price }).subscribe({
    next: () => this.load(),
    error: (err: any) => {
      this.errorMsg = '修改失败：' + (err.error?.message || err.message);
      this.cdr.detectChanges();
    },
  });
}
  editStock(p: Product): void {
    const stockStr = prompt(`修改 ${p.name} 的库存（当前 ${p.stock})`, String(p.stock));
    if (stockStr == null) return;
    const stock = parseInt(stockStr, 10);
    if (isNaN(stock) || stock < 0) {
      alert('库存不合法');
      return;
    }
    this.api.updateProduct(p.name, { stock }).subscribe({
      next: () => this.load(),
      error: (err: any) => {
        this.errorMsg = '修改失败：' + (err.error?.message || err.message);
        this.cdr.detectChanges();
      },
    });
  }

  del(name: string): void {
    if (!confirm(`确认删除 ${name}?`)) return;
    this.api.deleteProduct(name).subscribe({
      next: () => this.load(),
      error: (err: any) => {
        this.errorMsg = '删除失败：' + (err.error?.message || err.message);
        this.cdr.detectChanges();
      },
    });
  }

  create(): void {
    const name = prompt('商品名？');
    if (!name) return;
    const priceStr = prompt('价格？');
    if (priceStr == null) return;
    const stockStr = prompt('库存？');
    if (stockStr == null) return;

    const price = parseFloat(priceStr);
    const stock = parseInt(stockStr, 10);
    if (isNaN(price) || price < 0) { alert('价格不合法'); return; }
    if (isNaN(stock) || stock < 0) { alert('库存不合法'); return; }

    this.api.addProduct({ name, price, stock }).subscribe({
      next: () => this.load(),
      error: (err: any) => {
        this.errorMsg = '新增失败：' + (err.error?.message || err.message);
        this.cdr.detectChanges();
      },
    });
  }
}