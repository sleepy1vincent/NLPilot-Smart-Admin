import { Routes } from '@angular/router';
import {Chat} from '../app/components/chat/chat'
import {ProductList} from '../app/components/product-list/product-list';
import { SalesList } from './components/sales-list/sales-list';
import { PurchasesList } from './components/purchases-list/purchases-list';
export const routes: Routes = 
[
    { path: '', redirectTo: 'chat', pathMatch: 'full' },
    {path:'chat',component:Chat},
    {path:'products',component:ProductList},
    {path:'sales',component:SalesList},
    { path: 'purchases', component: PurchasesList }
];
