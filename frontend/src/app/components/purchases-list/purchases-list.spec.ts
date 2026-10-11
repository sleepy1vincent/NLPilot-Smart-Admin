import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PurchasesList } from './purchases-list';

describe('PurchasesList', () => {
  let component: PurchasesList;
  let fixture: ComponentFixture<PurchasesList>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PurchasesList],
    }).compileComponents();

    fixture = TestBed.createComponent(PurchasesList);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
