-- Resumind AI schema for Supabase (Postgres). RLS is enabled with no policies so the
-- public Supabase API (anon key) cannot read anything; only the FastAPI backend, which
-- connects with the database connection string, can.
create table if not exists public.users(
  id bigint generated always as identity primary key,
  name text not null, email text not null unique, pw text not null,
  created timestamptz not null default now());
create table if not exists public.resumes(
  id bigint generated always as identity primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  filename text not null, text text not null, parsed text not null, analysis text not null,
  created timestamptz not null default now());
create table if not exists public.jobs(
  id bigint generated always as identity primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  title text not null, description text not null, created timestamptz not null default now());
create table if not exists public.matches(
  id bigint generated always as identity primary key,
  resume_id bigint not null references public.resumes(id) on delete cascade,
  job_id bigint not null references public.jobs(id) on delete cascade,
  score int not null, result text not null, created timestamptz not null default now());
create table if not exists public.messages(
  id bigint generated always as identity primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  role text not null, content text not null, created timestamptz not null default now());
create index if not exists ix_resumes_user on public.resumes(user_id);
create index if not exists ix_jobs_user on public.jobs(user_id);
create index if not exists ix_matches_resume on public.matches(resume_id);
create index if not exists ix_messages_user on public.messages(user_id);
alter table public.users enable row level security;
alter table public.resumes enable row level security;
alter table public.jobs enable row level security;
alter table public.matches enable row level security;
alter table public.messages enable row level security;

revoke all on table public.users, public.resumes, public.jobs, public.matches, public.messages from anon, authenticated;

create table if not exists public.applications(
  id bigint generated always as identity primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  company text not null, role text not null, status text not null default 'Saved',
  notes text not null default '',
  resume_id bigint references public.resumes(id) on delete set null,
  job_id bigint references public.jobs(id) on delete set null,
  created timestamptz not null default now());
create table if not exists public.interviews(
  id bigint generated always as identity primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  question text not null, answer text not null, score int not null, feedback text not null,
  created timestamptz not null default now());
create index if not exists ix_applications_user on public.applications(user_id);
create index if not exists ix_interviews_user on public.interviews(user_id);
alter table public.applications enable row level security;
alter table public.interviews enable row level security;
revoke all on table public.applications, public.interviews from anon, authenticated;

create table if not exists public.audit_log(
  id bigint generated always as identity primary key,
  user_id bigint references public.users(id) on delete set null,
  event text not null, ip text not null default '', detail text not null default '',
  created timestamptz not null default now());
create index if not exists ix_audit_user on public.audit_log(user_id);
alter table public.audit_log enable row level security;
revoke all on table public.audit_log from anon, authenticated;
