# Upbit API를 이용한 간이 리밸런싱 앱

- 보유중인 특정 Ticker에 대해, 선택한 비율과 금액으로 정기적으로 리밸런싱을 실시하는 어플리케이션
- 여기서 리밸런싱이란, 설정한 가격과 비율로 매수/매도를 실시하는 것을 의미함.
- 예를 들어, 설정한 가격이 현재가의 5%, 비율이 보유 수량의 10%라고 할 경우, 어플리케이션은 아래와 같은 동작을 실시
  - 현재가 +5% (105%) 의 가격으로, 보유 수량의 10% 분에 대하여 매도 주문
  - 현재가 -5% (95%) 의 가격으로, 보유 수량의 10% 분에 대하여 매수 주문
  - 어플리케이션은 설정한 Term마다 해당 주문이 종료되었는지를 확인하고, 매도/매수 주문이 둘 다 종료되었을 경우에는 다시 현재의 가격과 보유 수량을 취득하여 지정된 가격/비율로 다시 매도/매수 주문을 넣음

## Setting

### 사전 준비

#### pyenv

이하 블로그의 내용을 참조하여, pyenv 를 설치할 것

- [Windows에서 pyenv 설치](https://idenrai.tistory.com/277)
- [Mac에서 pyenv 설치](https://idenrai.tistory.com/273)

#### poetry

이하 블로그의 내용을 참조하여, poetry 를 설치할 것

- [poetry 사용법](https://idenrai.tistory.com/289)

### 개발 환경 구축

Poetry를 이용하여 개발 환경 구축

```shell
make shell
```

```shell
make install
```

### 환경변수 설정

`.env.sample` 을 복사하여 `.env` 파일을 작성

```shell
ACCESS_KEY=<Upbit Access Key>
SECRET_KEY=<Upbit Secret Key>
```

## Run

```shell
make serve
```
