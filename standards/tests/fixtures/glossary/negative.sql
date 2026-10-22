create table deudas (
  deuda_id bigint primary key,
  client_id bigint not null,
  portfolio_upload_id bigint
);
