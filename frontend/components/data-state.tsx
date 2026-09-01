import React from "react";

export type DataStateType = "loading" | "empty" | "error";

interface DataStateProps {
  errorMessage?: string;
  state: DataStateType;
}

const state_content: Record<DataStateType, { message: string; title: string }> = {
  empty: {
    message: "표시할 운영 데이터가 없습니다.",
    title: "운영 데이터 없음",
  },
  error: {
    message: "대시보드 데이터를 불러오지 못했습니다.",
    title: "데이터 조회 오류",
  },
  loading: {
    message: "데이터를 불러오는 중입니다.",
    title: "운영 데이터 로딩 중",
  },
};

export function DataState({ errorMessage, state }: Readonly<DataStateProps>) {
  const content = state_content[state];
  const role = state === "error" ? "alert" : "status";

  return (
    <section aria-live="polite" className={`data-state data-state--${state}`} role={role}>
      <h1>{content.title}</h1>
      <p>{state === "error" && errorMessage ? errorMessage : content.message}</p>
    </section>
  );
}
