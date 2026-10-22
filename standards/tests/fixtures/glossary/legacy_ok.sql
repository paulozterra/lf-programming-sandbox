alter table lf_client.client_accounts add column phone_verified_at timestamptz;
select client_id from lf_client.client_phone_bindings;
