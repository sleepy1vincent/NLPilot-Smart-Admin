import { Routes } from '@angular/router';
import {Chat} from '../app/components/chat/chat'
import {ProductList} from '../app/components/product-list/product-list';
export const routes: Routes = 
[
    { path: '', redirectTo: 'chat', pathMatch: 'full' },
    {path:'chat',component:Chat},
    {path:'products',component:ProductList}
];
