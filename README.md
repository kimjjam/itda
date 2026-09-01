# 잇다 (ITDA)

외국인 근로자와 씬파일러가 비금융 증빙을 정리해 금융기관 심사용 근거자료 리포트를 만드는 데모 서비스입니다.

## 구성

- `frontend/`: React, TypeScript, Vite
- `backend/`: FastAPI
- `database/`: Neon Postgres 스키마와 상품 시드

실제 마이데이터 연동이나 자체 신용평가는 수행하지 않습니다. 금융상품의 최종 심사와 조건은 각 금융기관이 결정합니다.

## 로컬 실행

1. `.env.example`의 키를 참고해 OS 또는 배포 플랫폼에 환경변수를 설정합니다. 시크릿 파일은 커밋하지 않습니다.
2. 백엔드를 실행합니다.

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

3. 별도 터미널에서 프런트엔드를 실행합니다.

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

환경변수가 없으면 저장·외부 조회·문서 자동추출을 생략하고, 나머지 흐름은 명시적인 fallback 상태로 계속 동작합니다. 운영 시에는 `LLM_API_BASE_URL`에 OpenAI 호환 API의 `/v1` 기준 URL을 설정합니다.

## 검증

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

cd ..\frontend
npm run build
```

백엔드 `/api/analyze/stream`은 KOSIS → 한국수출입은행 환율 → 룰 기반 근거 확인 → LLM 설명 순으로 NDJSON 이벤트를 보냅니다. 외부 API는 HTTP 200 안의 오류 코드까지 확인하며, 마지막 정상값 캐시가 없으면 임의 숫자를 만들지 않고 해당 지표를 제외합니다.

## Neon Postgres + Vercel Private Blob

[`database/schema.sql`](./database/schema.sql)은 익명 사용자, 증빙, 비공개 문서 URL, 리포트, 항목, 상품 카탈로그를 생성합니다. 2026-09-01 연결된 Neon DB에 스키마와 상품 12건을 적용했으며, 백엔드는 활성 상품을 Neon에서 읽고 조회 실패 시 검증된 정적 목록으로 fallback합니다. 브라우저에는 연결 문자열을 전달하지 않습니다.

증빙 원본은 Vercel Private Blob에 저장하고, Neon에는 Private Blob URL과 추출 결과만 기록합니다. `BLOB_READ_WRITE_TOKEN`은 읽기·쓰기 권한이 있는 서버 시크릿이므로 Render 백엔드에만 설정하고 프런트엔드에 노출하지 않습니다.

## 배포 준비

- 프런트: Vercel 프로젝트의 Root Directory를 `frontend`, Build Command를 `npm run build`, Output Directory를 `dist`로 설정합니다. `VITE_API_BASE_URL`에는 배포된 백엔드의 `/api` URL을 넣습니다.
- 백엔드: 루트의 [`render.yaml`](./render.yaml)은 Render 무료 컴퓨트와 `/health` 검사를 사용합니다. Render에는 Neon의 pooled `DATABASE_URL`과 Private Blob의 `BLOB_READ_WRITE_TOKEN`을 서버 시크릿으로 설정합니다.
- UptimeRobot: Render 배포 후 `Keyword` 모니터 URL을 `https://<render-service>.onrender.com/health`, 키워드를 `"status":"ok"`, 간격을 무료 플랜의 5분으로 설정하고 키워드가 없을 때 알림을 받습니다. 외부 요청이 Render의 15분 유휴 시간을 갱신하는 방식이지만 무슬립을 보장하지는 않으며, Render의 임의 재시작과 workspace당 월 750 무료 인스턴스 시간 제한은 그대로 적용됩니다. 2026-09-07 11:00 전에 모니터와 알림을 켜고 실제 응답을 확인합니다.
- Vercel Hobby는 정적 파일을 슬립 없이 제공하지만 개인·비상업 용도 조건이 있습니다. 팀 계정 사용 조건에 따라 Pro가 필요할 수 있습니다.

스키마 재적용과 실제 배포는 데이터·비용에 영향을 줄 수 있으므로 실행 전 대상 환경을 확인합니다.

## 외부 자료 기준

- KOSIS: `https://kosis.kr/openapi/Param/statisticsParameterData.do`
- 한국수출입은행: 2026년 구 도메인 종료를 반영한 `https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON`
- 상품 카탈로그: 2026-08-31 공식 금융사 자료 확인 기준. 판매 중단이 확인된 한화·대신 상품은 DB 이력에는 남기되 매칭 응답에서 제외합니다.
