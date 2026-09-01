import type { NextConfig } from "next";

// rewrites()는 빌드 시점에 .next/routes-manifest.json으로 구워지므로, 이 값은 런타임 env가
// 아니라 빌드 시점에 정해진다. Docker에서는 API_INTERNAL_BASE_URL 빌드 인자로 전달한다.
const api_internal_base_url =
  process.env.API_INTERNAL_BASE_URL ?? "http://127.0.0.1:8000";

const next_config: NextConfig = {
  // 실행에 필요한 파일만 추린 .next/standalone 출력을 함께 생성해 컨테이너 이미지를 줄인다.
  // 기존 .next 출력은 그대로 남으므로 `npm run start`(next start)도 계속 동작한다.
  output: "standalone",
  async rewrites() {
    return [
      {
        destination: `${api_internal_base_url}/api/:path*`,
        source: "/api/:path*",
      },
    ];
  },
};

export default next_config;
