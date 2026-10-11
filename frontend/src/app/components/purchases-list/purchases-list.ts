import { ChangeDetectorRef, Component, inject, OnInit } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { CommonModule } from '@angular/common';

@Component({
  imports: [CommonModule],
  selector: 'app-sales-list',
  styleUrl: './purchases-list.css',
  templateUrl: './purchases-list.html',
})
export class PurchasesList implements OnInit{
  sales:any[] = [];
  loading=false;
  errorMsg='';
  days:number|null =30;
  
  private api=inject(ApiService)
  private cdr=inject(ChangeDetectorRef);

  ngOnInit(): void {
    this.load();
  }
  load():void
  {
    this.loading=true;
    this.errorMsg='';
    this.api.getBought(undefined,this.days??undefined).subscribe({
      next:(res:any)=>{
        this.sales=res.data??[];
        this.loading=false;
        this.cdr.detectChanges();
      },
      error:(err:any)=>{
        this.errorMsg='加载失败'+(err.error?.message||err.message);
        this.loading=false;
        this.cdr.detectChanges();
      },
    });
  }
  changeDays(d:number|null):void{
    this.days=d;
    this.load();
  }
}
