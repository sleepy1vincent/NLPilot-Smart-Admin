create table product_lists
(
    id int primary key auto_increment comment '商品编号',
    name varchar(128) not null comment '商品名',
    price decimal(10,2) not null comment '价格',
    stock int not null comment '库存',
    last_update datetime default current_timestamp on update current_timestamp,
    unique key unique_name(name)
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
create table conversations
(
  id int primary key auto_increment comment '对话编号',
  last_update datetime default current_timestamp,
  created_at datetime default current_timestamp
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
create table messages
(
    id int primary key  auto_increment comment '记录编号',
    belong_id int not null comment '所从属的对话',
    content text not null comment '对话内容',
    role enum('ai','user') not null comment '发送方',
    last_update datetime default current_timestamp on update current_timestamp,
    key idx_belong(belong_id),
    foreign key (belong_id) references conversations(id) on delete cascade
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;