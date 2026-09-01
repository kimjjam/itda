create extension if not exists pgcrypto;

create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now()
);

create table if not exists public.evidences (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  payload jsonb not null default '{}'::jsonb,
  self_reported_risk boolean not null default false,
  simulation_input boolean not null default true,
  created_at timestamptz not null default now()
);

comment on column public.evidences.self_reported_risk is
  '사용자가 데모 화면에서 직접 입력한 시뮬레이션 값이며 실제 금융거래 조회 결과가 아님';
comment on column public.evidences.simulation_input is
  '실제 마이데이터 연동이 아닌 시뮬레이션 입력 여부';

create table if not exists public.document_uploads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  category text not null check (category in ('employment', 'telecom', 'insurance', 'remittance')),
  storage_url text not null unique,
  extracted_fields jsonb not null default '{}'::jsonb,
  extraction_status text not null check (extraction_status in ('extracted', 'needs_review', 'failed')),
  created_at timestamptz not null default now()
);

create table if not exists public.credit_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  evidence_strength integer not null check (evidence_strength between 0 and 100),
  evidence_level text not null check (evidence_level in ('충분', '보통', '추가 자료 필요')),
  summary text not null,
  risk_alert boolean not null default false,
  risk_alert_message text,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.report_items (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references public.credit_reports(id) on delete cascade,
  item_key text not null,
  title text not null,
  value text not null,
  strength text not null check (strength in ('strong', 'moderate', 'limited')),
  explanation text not null,
  source text not null,
  created_at timestamptz not null default now(),
  unique (report_id, item_key)
);

create table if not exists public.matched_products (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  name text not null,
  category text not null check (category in (
    '저축은행_신용대출',
    '시중은행_전세대출',
    '시중은행_외국인신용대출'
  )),
  eligible_visas text[] not null default '{}',
  limit_text text,
  rate_text text,
  requirement_text text,
  source_url text,
  verified_at date,
  is_active boolean not null default true,
  unique (provider, name)
);

insert into public.matched_products (
  provider, name, category, eligible_visas, limit_text, rate_text,
  requirement_text, source_url, verified_at, is_active
)
values
  (
    'OK저축은행', 'Hi-OK론', '저축은행_신용대출', array['E-9','E-7','F-2','F-6','D-2'],
    '100만원~6,000만원', '연 14.23%~19.99% (2026-05-01 기준)',
    '소득증빙 가능, NICE 300점 이상, 내부 심사기준 적용',
    'https://m.oksavingsbank.com/product/lon/frgn.jsp?addUrl=%2F%23%2FgdsLonCrdaDtl&lonGdsSqno=172&menuCd=00170',
    '2026-08-31', true
  ),
  (
    '웰컴저축은행', '웰컴외국인대출', '저축은행_신용대출', array['E-9','E-7','D-2'],
    '최대 3,000만원', '연 7.61%~19.90% (2026-07-15 기준)',
    '체류기간 만료까지 1개월 이상, NICE 300점 이상, 소득·심사 결과별 차등',
    'https://m.welcomebank.co.kr/ib20/mnu/MWBDSP000000?prdCd=1275101184&sysDsCd=02',
    '2026-08-31', true
  ),
  (
    '예가람저축은행', 'Oh! YES loan', '저축은행_신용대출', array['E-9','E-7','F-2','F-6'],
    '최대 4,000만원', '연 11.5%~19.9%',
    '대한민국 체류 및 소득증빙 가능한 외국인 근로자, 내부 심사기준 적용',
    'https://nsl.yegaramsb.co.kr/lon/inq/loanList.frm',
    '2026-08-31', true
  ),
  (
    '한화저축은행', '외국인 신용대출(K-Loan)', '저축은행_신용대출', array['E-9','F-4','F-5','F-6'],
    '300만~1,500만원 (중단 전)', '연 14.5%~16.5% (중단 전)',
    '2021-04-08 일시중단', 'https://www.hanwhasbank.com/ProdList_001.act?rnum=66',
    '2026-08-31', false
  ),
  (
    '대신저축은행', '하이코리아(Hi-Korea)', '저축은행_신용대출', array[]::text[],
    '100만~1,500만원 (중단 전)', '연 18.52%~19.90% (중단 전)',
    '2021-05 판매중단, 구 상세 KCB 445점 이상',
    'https://bank.daishin.com/sub.do?code=02_etcp01', '2026-08-31', false
  ),
  (
    'KB국민은행', 'KB WELCOME PLUS 전세자금대출', '시중은행_전세대출', array['D-2','E-7','F-2','F-6'],
    '최대 2억원 (보증·임차보증금 조건 적용)', '연 4.23%~5.74% (2026-08-27 공시 범위)',
    '국내소득 3개월 이상, SGI 보증 가능, 비자 잔여기간 등 세부요건 적용',
    'https://obank.kbstar.com/quics?QSL=F&cc=b104363%3Ab104516&isNew=N&page=C103507&prcode=LN20001120',
    '2026-08-31', true
  ),
  (
    '신한은행', 'SOL글로벌 전세대출(서울보증_외국인)', '시중은행_전세대출', array[]::text[],
    null, null, '현행 공식 문서에서 상품명만 확인됨. 세부 조건은 금융기관 확인 필요',
    'https://img.shinhan.com/sbank2016/seol/20170630814200000030LC000030.PDF',
    '2026-08-31', true
  ),
  (
    '광주은행', 'TOGETHER외국인신용대출', '시중은행_외국인신용대출', array[]::text[],
    '100만~5,000만원 (2025-03-31 공시)', null,
    '국내 장기체류 등록외국인·거소신고 동포 중 요건을 충족한 급여소득자',
    'https://www.kjbank.com/ib20/mnu/FPMLOAN020001', '2026-08-31', true
  ),
  (
    '전북은행', 'JB Bravo KOREA 대출', '시중은행_외국인신용대출', array[]::text[],
    null, null, '체류자격별 세부 대상·한도·금리는 금융기관 확인 필요',
    'https://www.jbbank.co.kr/loan_gdnc_cdln.act', '2026-08-31', true
  ),
  (
    '부산은행', 'BNK웰컴 글로벌대출', '시중은행_외국인신용대출', array[]::text[],
    null, null, '외국인 근로자 대상. 체류자격·한도·금리는 금융기관 확인 필요',
    'https://www.busanbank.co.kr/ib20/mnu/FPMLON092001001', '2026-08-31', true
  ),
  (
    '하나은행', '하나 외국인 EZ Loan', '시중은행_외국인신용대출', array['E-7','E-9'],
    '100만~1,000만원', null,
    '외국인등록증 보유, 국내 거주·현 직장 급여소득 각 3개월 이상, 거래외국환 지정. E-9는 최초 입국자',
    'https://www.kebhana.com/cont/mall/mall08/mall0802/mall080204/1510586_115200.jsp?_menuNo=98786',
    '2026-09-01', true
  ),
  (
    'BNK경남은행', 'K dream 외국인신용대출', '시중은행_외국인신용대출', array[]::text[],
    null, null,
    '국내 거주 외국인 근로자 전용. 세부 체류자격·한도·금리는 금융기관 확인 필요',
    'https://www.bnkfg.com/download?seq=6565', '2026-09-01', true
  )
on conflict (provider, name) do update set
  category = excluded.category,
  eligible_visas = excluded.eligible_visas,
  limit_text = excluded.limit_text,
  rate_text = excluded.rate_text,
  requirement_text = excluded.requirement_text,
  source_url = excluded.source_url,
  verified_at = excluded.verified_at,
  is_active = excluded.is_active;
