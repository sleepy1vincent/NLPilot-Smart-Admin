export interface Product {
  id: number;
  name: string;
  price: string;
  stock: number;
  last_update: string; 
}
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}
export interface ProductCreate {
  name: string;
  price: number;
  stock: number;
}

export interface ProductUpdate {
  price?: number;
  stock?: number;
}