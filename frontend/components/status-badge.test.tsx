import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./status-badge";

describe("StatusBadge", () => {
  it("renders an icon and the Korean danger severity label", () => {
    const markup = renderToStaticMarkup(<StatusBadge severity="위험" />);

    expect(markup).toContain("위험");
    expect(markup).toContain('aria-label="위험 상태"');
  });

  it("does not downgrade a caution severity to danger", () => {
    const markup = renderToStaticMarkup(<StatusBadge severity="주의" />);

    expect(markup).toContain("주의");
    expect(markup).not.toContain("위험 상태");
  });
});
