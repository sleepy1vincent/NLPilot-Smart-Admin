import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Product, ApiResponse, ProductCreate, ProductUpdate } from '../models/product.model';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = 'http://localhost:5001/api';

  constructor(private http: HttpClient) {}

  getProducts(name?: string): Observable<ApiResponse<Product[]>> {
    const url = name
      ? `${this.base}/products?name=${encodeURIComponent(name)}`
      : `${this.base}/products`;
    return this.http.get<ApiResponse<Product[]>>(url);
  }
  addProduct(product: ProductCreate): Observable<ApiResponse<{ id: number }>> {
    return this.http.post<ApiResponse<{ id: number }>>(`${this.base}/products`, product);
  }
  updateProduct(name: string, fields: ProductUpdate): Observable<ApiResponse<any>> {
    return this.http.put<ApiResponse<any>>(
      `${this.base}/products/${encodeURIComponent(name)}`,
      fields,
    );
  }
  deleteProduct(name: string): Observable<ApiResponse<any>> {
    return this.http.delete<ApiResponse<any>>(
      `${this.base}/products/${encodeURIComponent(name)}`,
    );
  }
  chat(message: string, history: any[] = []): Observable<any> {
    return this.http.post<any>(`${this.base}/chat`, { message, history });
  }
  confirm(action: string, target: string,data:any): Observable<any> {
    return this.http.post<any>(`${this.base}/chat/confirm`, { action, target,data });
  }

  getSales(name?: string, days?: number): Observable<ApiResponse<any[]>> {
    let params = new HttpParams();
    if (name) params = params.set('name', name);
    if (days != null) params = params.set('days', days.toString());
    return this.http.get<ApiResponse<any[]>>(`${this.base}/sales`, { params });
  }
  getBought(name?:string,days?:number):Observable<ApiResponse<any[]>>{
    let params = new HttpParams();
    if(name) params=params.set('name',name);
    if(days!=null) params=params.set('days',days.toString());
    return this.http.get<ApiResponse<any[]>>(`${this.base}/purchases`, { params })
  }
}