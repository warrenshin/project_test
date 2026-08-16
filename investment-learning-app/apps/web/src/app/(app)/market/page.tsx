"use client";

import Link from "next/link";
import { useState } from "react";
import { searchInstruments } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "@/components/States";

export default function MarketPage() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const results = useAsync(() => searchInstruments(submittedQuery), [submittedQuery]);

  return (
    <div className="stack">
      <h1>종목 검색</h1>
      <p className="muted">
        현재는 데모 종목 4개(삼성전자, SK하이닉스, AAPL, MSFT)만 조회할 수 있습니다. 시세는 실시간이
        아닌 샘플 데이터입니다.
      </p>

      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmittedQuery(query.trim());
        }}
      >
        <input
          type="text"
          placeholder="종목명 또는 코드 (예: SK하이닉스, 000660)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn btn-primary" type="submit">
          검색
        </button>
      </form>

      {results.loading && <LoadingBlock label="종목을 검색하는 중입니다..." />}
      {results.error && <ErrorBlock message={results.error} onRetry={results.reload} />}
      {results.data && results.data.length === 0 && (
        <EmptyBlock message="검색 결과가 없습니다. 데모 종목명(삼성전자, SK하이닉스, AAPL, MSFT) 또는 코드로 검색해보세요." />
      )}

      <div className="stack">
        {results.data?.map((inst) => (
          <Link
            key={inst.id}
            href={`/market/${inst.id}`}
            className="row-between card"
            style={{ marginBottom: 0, textDecoration: "none" }}
          >
            <div>
              <strong>{inst.name}</strong>
              <p className="muted" style={{ margin: 0 }}>
                {inst.ticker} · {inst.exchange} · {inst.currency}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
