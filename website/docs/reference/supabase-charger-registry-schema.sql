-- Supabase / PostgreSQL schema base for charger registry by location
-- Purpose: ingest arbitrary Excel layouts per building/location and normalize charger records.

begin;

create table if not exists locations (
  location_id uuid primary key default gen_random_uuid(),
  nombre_edificio text not null,
  direccion text,
  ciudad text,
  provincia text,
  codigo_interno text,
  fuente_principal text,
  notas text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (nombre_edificio, direccion)
);

create table if not exists source_documents (
  source_document_id uuid primary key default gen_random_uuid(),
  location_id uuid references locations(location_id) on delete cascade,
  nombre_archivo text not null,
  ruta_archivo text,
  tipo_archivo text not null default 'xlsx',
  hoja text,
  fecha_carga timestamptz not null default now(),
  hash_archivo text,
  version text,
  observaciones text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (location_id, nombre_archivo, hash_archivo)
);

create table if not exists extraction_rules (
  rule_id uuid primary key default gen_random_uuid(),
  location_id uuid references locations(location_id) on delete cascade,
  nombre_regla text not null,
  prioridad integer not null default 100,
  patrones_columna jsonb not null default '[]'::jsonb,
  patrones_valor jsonb not null default '[]'::jsonb,
  campos_objetivo jsonb not null default '[]'::jsonb,
  activa boolean not null default true,
  notas text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists chargers (
  charger_id uuid primary key default gen_random_uuid(),
  location_id uuid not null references locations(location_id) on delete cascade,
  source_document_id uuid references source_documents(source_document_id) on delete set null,
  source_row_ref text,
  plaza text not null,
  planta text,
  serie text not null,
  id_colonial text,
  ip inet,
  username text,
  password text,
  ssid_wifi text,
  wifi_password text,
  irisd_url text,
  estado text not null default 'pendiente',
  extractor_status text not null default 'parcial',
  confidence_score integer not null default 0 check (confidence_score between 0 and 100),
  comentarios text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (location_id, plaza),
  unique (location_id, id_colonial)
);

create index if not exists idx_chargers_location_plaza on chargers(location_id, plaza);
create index if not exists idx_chargers_location_serie on chargers(location_id, serie);

create table if not exists charger_raw_rows (
  raw_row_id uuid primary key default gen_random_uuid(),
  source_document_id uuid not null references source_documents(source_document_id) on delete cascade,
  sheet_name text,
  row_number integer,
  raw_values jsonb not null,
  detected_fields jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (source_document_id, sheet_name, row_number)
);

create index if not exists idx_chargers_location_id on chargers(location_id);
create index if not exists idx_chargers_ip on chargers(ip);
create index if not exists idx_chargers_serie on chargers(serie);
create index if not exists idx_chargers_id_colonial on chargers(id_colonial);
create index if not exists idx_rules_location_priority on extraction_rules(location_id, prioridad desc);
create index if not exists idx_raw_rows_source on charger_raw_rows(source_document_id);

-- Helper constraints / conventions
-- 1) IP-based routing rules:
--    10.x.x.x         -> Colonial network, VPN required
--    192.168.31.x     -> local agent machine network, no VPN required
-- 2) serie must be stored as text to avoid Excel scientific notation loss.
-- 3) comentarios should preserve free text and replacement notes like 'SE REEMPLAZO'.
-- 4) metadata can store extra fields found in non-standard spreadsheets.

-- Optional trigger for updated_at could be added later if desired.

commit;
