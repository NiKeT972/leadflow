-- LeadFlow tables. Run once in Supabase → SQL Editor.
-- The app uses the service-role key from server env vars only; RLS stays on with no policies,
-- so the public anon key can't read anyone's leads.

create table if not exists public.leads (
  id          uuid primary key,
  business_id text not null,
  enquiry     jsonb not null,
  result      jsonb not null,          -- {state, paused_at, token}: the workflow output and signed resume token
  status      text not null default '',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists leads_business_created on public.leads (business_id, created_at desc);

create table if not exists public.businesses (
  id          text primary key,         -- e.g. "glow-studio"; used as business_id by intake
  profile     jsonb not null,           -- same shape as the settings page (leadflow.profiles.Profile)
  docs        jsonb not null default '[]'::jsonb,
  updated_at  timestamptz not null default now()
);

alter table public.leads enable row level security;
alter table public.businesses enable row level security;
