// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { use_api_data } from "./use-api-data";

afterEach(() => {
  cleanup();
});

function ApiProbe({ loader }: Readonly<{ loader: () => Promise<string[]> }>) {
  const { data, error_message, is_loading } = use_api_data(loader);

  if (is_loading) {
    return <p>loading</p>;
  }
  if (error_message) {
    return <p>{error_message}</p>;
  }
  return <p>{data?.join(",") || "empty"}</p>;
}

describe("use_api_data", () => {
  it("moves from loading to resolved API data", async () => {
    render(<ApiProbe loader={vi.fn().mockResolvedValue(["loaded"])} />);

    expect(screen.getByText("loading")).toBeTruthy();
    expect(await screen.findByText("loaded")).toBeTruthy();
  });

  it("exposes the API error message", async () => {
    render(<ApiProbe loader={vi.fn().mockRejectedValue(new Error("조회 실패"))} />);

    expect(await screen.findByText("조회 실패")).toBeTruthy();
  });
});
