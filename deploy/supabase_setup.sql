-- 해외주식 앱 전용 공간 만들기 (Supabase SQL Editor 에서 한 번만 실행)
-- 실행 전: 아래 'CHANGE_ME' 를 직접 정한 비밀번호로 바꾸세요.
--          비밀번호는 영문과 숫자만 쓰세요 (특수문자는 접속 주소에서 오류가 날 수 있음).

-- 1) 해외 앱 전용 계정
create role overseas_app with login password 'CHANGE_ME';

-- 2) 해외 앱 전용 공간. 이 계정이 주인이라 표는 앱이 처음 켜질 때 스스로 만듭니다.
grant overseas_app to postgres;
create schema overseas authorization overseas_app;

-- 3) Supabase 자동 공개 API 용 계정은 이 공간에 접근하지 못하게 막기
revoke all on schema overseas from anon, authenticated;

-- 확인: 아래 결과에 overseas | overseas_app 한 줄이 나오면 성공
select schema_name, schema_owner from information_schema.schemata where schema_name = 'overseas';
