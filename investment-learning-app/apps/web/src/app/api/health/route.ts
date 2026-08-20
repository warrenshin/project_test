// Docker HEALTHCHECK 및 컨테이너 오케스트레이터용 liveness 엔드포인트.
// Next.js 서버 프로세스가 요청을 처리할 수 있는지만 확인한다 — 백엔드 API나
// 외부 서비스에는 의존하지 않는다(그쪽 장애로 이 컨테이너가 재시작되면 안 된다).
export async function GET() {
  return Response.json({ status: "ok" });
}
