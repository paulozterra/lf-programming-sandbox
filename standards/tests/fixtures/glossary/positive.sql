-- estado de la oferta: el comentario en español no se revisa
create table offers (
  offer_id bigint generated always as identity primary key,
  payment_status text not null default 'pendiente',
  currency text not null,
  paid_amount numeric(18,2) not null
);
