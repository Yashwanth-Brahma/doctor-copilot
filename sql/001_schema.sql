create extension if not exists vector;   -- used from v3

create table patients (
  id          text primary key,          -- FHIR Patient id
  name        text,
  birth_date  date,
  sex         text
);

create table encounters (
  id          text primary key,
  patient_id  text references patients(id),
  start_at    timestamptz,
  end_at      timestamptz,
  class       text,
  type        text
);

create table conditions (
  id              text primary key,
  patient_id      text references patients(id),
  code            text,
  display         text,
  onset_at        timestamptz,
  abated_at       timestamptz,
  clinical_status text,
  is_disorder     boolean
);

create table medications (
  id           text primary key,
  patient_id   text references patients(id),
  encounter_id text,
  rxnorm       text,
  display      text,
  status       text,
  authored_at  timestamptz
);

create table observations (
  id           text primary key,
  patient_id   text references patients(id),
  encounter_id text,
  category     text,       -- laboratory | vital-signs | survey
  loinc        text,
  concept      text,       -- mapped concept, e.g. 'creatinine'
  display      text,
  value        numeric,
  unit         text,
  effective_at timestamptz,
  ref_low      numeric,
  ref_high     numeric
);

create index on observations (patient_id, concept, effective_at);

-- Supabase exposes public tables via REST. RLS on + no policies = REST returns nothing;
-- the backend uses the direct database connection.
alter table patients     enable row level security;
alter table encounters   enable row level security;
alter table conditions   enable row level security;
alter table medications  enable row level security;
alter table observations enable row level security;