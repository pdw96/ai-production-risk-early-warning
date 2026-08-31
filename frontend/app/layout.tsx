import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI 생산 리스크 조기경보",
  description: "생산 운영 통제실",
};

const navigation_items = [
  { href: "/", label: "운영 현황" },
  { href: "/orders", label: "오더" },
  { href: "/materials", label: "자재" },
  { href: "/risks", label: "리스크" },
];

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <div className="control-room min-h-screen">
          <aside className="control-room__rail">
            <div className="control-room__brand">
              <span className="control-room__eyebrow">OPERATIONS CONTROL</span>
              <strong className="control-room__title">AI 생산 리스크 조기경보</strong>
            </div>
            <nav aria-label="주요 메뉴" className="control-room__navigation">
              {navigation_items.map((item) => (
                <Link href={item.href} key={item.href}>
                  {item.label}
                </Link>
              ))}
            </nav>
          </aside>
          <main className="control-room__content">{children}</main>
        </div>
      </body>
    </html>
  );
}
