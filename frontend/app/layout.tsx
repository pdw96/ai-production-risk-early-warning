import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "./globals.css";
import { navigation_groups, type NavigationNode } from "../lib/navigation";

export const metadata: Metadata = {
  title: "AI 생산 리스크 조기경보",
  description: "생산 운영 통제실",
};

/**
 * 메뉴 트리를 깊이만큼 들여써서 그린다. 링크가 없는 노드는 하위 항목을 묶는
 * 이름표라 `<p>` 로 낸다 — 누를 수 없는 것을 링크처럼 보이게 하면 안 된다.
 */
function NavigationNodes({
  depth,
  nodes,
}: Readonly<{ depth: number; nodes: NavigationNode[] }>) {
  return (
    <>
      {nodes.map((node) => (
        <div key={node.label}>
          {node.href ? (
            <Link data-depth={depth} href={node.href}>
              {node.label}
            </Link>
          ) : (
            <p className="control-room__navigation-branch" data-depth={depth}>
              {node.label}
            </p>
          )}
          {node.children ? (
            <NavigationNodes depth={depth + 1} nodes={node.children} />
          ) : null}
        </div>
      ))}
    </>
  );
}

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
              {navigation_groups.map((group) => (
                <div className="control-room__navigation-group" key={group.label}>
                  <p className="control-room__navigation-label">{group.label}</p>
                  <NavigationNodes depth={0} nodes={group.items} />
                </div>
              ))}
            </nav>
          </aside>
          <main className="control-room__content">{children}</main>
        </div>
      </body>
    </html>
  );
}
