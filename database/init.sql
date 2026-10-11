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
-- 销售记录表
CREATE TABLE IF NOT EXISTS sales (
    id           INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
    product_name VARCHAR(128)  NOT NULL COMMENT '商品名',
    quantity     INT           NOT NULL COMMENT '数量',
    unit_price   DECIMAL(10,2) NOT NULL COMMENT '单价',
    total        DECIMAL(10,2) NOT NULL COMMENT '总价',
    sold_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '销售时间',
    KEY idx_product (product_name),
    KEY idx_sold_at (sold_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='销售记录';

-- 进货记录表
CREATE TABLE IF NOT EXISTS purchases (
    id           INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
    product_name VARCHAR(128)  NOT NULL COMMENT '商品名',
    quantity     INT           NOT NULL COMMENT '数量',
    unit_price   DECIMAL(10,2) NOT NULL COMMENT '进货单价',
    total        DECIMAL(10,2) NOT NULL COMMENT '总价',
    purchased_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '进货时间',
    KEY idx_product (product_name),
    KEY idx_purchased_at (purchased_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='进货记录';