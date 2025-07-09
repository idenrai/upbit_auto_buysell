.PHONY: shell install serve

# Poetry 가상환경 활성화
shell:
	poetry run bash

# 종속성 설치
install:
	poetry lock
	poetry install --no-root

# 실행
serve:
	poetry run streamlit run app.py
