import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import { DataState } from "./data-state";

describe("DataState", () => {
  it("announces loading while dashboard data is being requested", () => {
    const markup = renderToStaticMarkup(<DataState state="loading" />);

    expect(markup).toContain("데이터를 불러오는 중입니다.");
    expect(markup).toContain('role="status"');
  });

  it("explains the empty dashboard state", () => {
    const markup = renderToStaticMarkup(<DataState state="empty" />);

    expect(markup).toContain("표시할 운영 데이터가 없습니다.");
  });

  it("presents an API error to the operator", () => {
    const markup = renderToStaticMarkup(
      <DataState errorMessage="서버 오류" state="error" />,
    );

    expect(markup).toContain("서버 오류");
    expect(markup).toContain('role="alert"');
  });
});
