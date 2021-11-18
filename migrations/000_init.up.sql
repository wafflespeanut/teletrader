CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE orders (
    order_id uuid NOT NULL DEFAULT uuid_generate_v4(),
    exchange_id bigint NULL,
    parent_id uuid NULL,
    create_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    symbol varchar(64) NULL,
    cancel_date timestamp without time zone NULL,
    price float NOT NULL,
    quantity float NOT NULL,
    order_type varchar(16) NOT NULL, -- INIT, STOP, TARGET
    filled boolean NOT NULL DEFAULT false,

    CONSTRAINT order_id_pk PRIMARY KEY (order_id)
    CONSTRAINT order_parent_fk FOREIGN KEY (parent_id) REFERENCES orders (order_id)
);

CREATE INDEX orders_create_date_idx ON orders(create_date);
CREATE INDEX orders_parent_idx ON orders (parent_id);
CREATE INDEX orders_exchange_idx ON orders (exchange_id);
