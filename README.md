# python_script

데이터 입출력 등의 간단한 처리를 위한 Python script 를 작성함에 있어, 아래의 기능을 제공하는 템플릿

- Poetry를 통한 패키지 관리 및 가상환경 설정
- 환경변수 관리
- YAML을 이용한 config 관리
- Log 기록
- JSON 읽기/쓰기
- 위의 기능을 이용하는 샘플 스크립트

## Setting

Poetry를 이용하여 개발 환경 구축

```shell
poetry install
```

```shell
poetry shell
```

## Sample Scripts

샘플 스크립트는 아래의 두가지 처리를 실시

- search_sample.py
  - `DynamoDB` 의 `Document Table` 에서 조건에 맞는 데이터를 검색하여 JSON파일로 저장
- update_sample.py
  - JSON파일을 읽어, 해당 데이터를 `DynamoDB` 의 `Document Table` 에서 논리삭제

### Seting

제공되는 스크립트는 Docker로 구동하는 DynamoDB Local 을 이용하고 있음

#### DynamoDB Local

동일 리포지토리의 `dynamodb_local` 를 참조

#### 환경변수

`.dev.env.sample` 을 복사하여 `.dev.env` 파일을 작성

### Run

#### search_sample

- env : 실행할 환경 (dev, stg, prd)

예시

```shell
python search_sample.py --env=dev
```

#### update_sample

- env : 실행할 환경 (dev, stg, prd)
- timestamp : `search_sample.py`의 실행 결과 `intermediate` 폴더 안에 생성되는 `YYYYmmDDHHMMSS` 폴더명

예시

```shell
python update_sample.py --env=dev --timestamp=20240706162914
```
