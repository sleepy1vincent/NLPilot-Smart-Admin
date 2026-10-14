import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { ProductList } from './product-list';

describe('ProductList', () => {
  it('应该能渲染商品列表', async () => {
    TestBed.configureTestingModule({
      imports: [ProductList],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const fixture = TestBed.createComponent(ProductList);
    const http = TestBed.inject(HttpTestingController);

    fixture.detectChanges();
    http.expectOne(r => r.url.includes('/api/products')).flush({
      code: 200, message: 'ok',
      data: [{ id: 1, name: '测试商品', price: '19.90', stock: 5, last_update: '2025-01-01 00:00:00' }],
    });
    http.match(r => r.url.includes('/api/sales')).forEach(r => r.flush({ code: 200, data: [], message: '' }));
    http.match(r => r.url.includes('/api/purchases')).forEach(r => r.flush({ code: 200, data: [], message: '' }));

    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('测试商品');
  });
});