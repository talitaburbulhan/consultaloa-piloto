"use client";

import { FormEvent, useEffect, useState } from "react";

type Evidence = {
  document: string;
  year: number;
  pdf_page: number;
  printed_page: string | null;
  original_text: string;
  filename: string;
  page_url: string;
};

type SourceReference = {
  id: number;
  document: string;
  year: number;
  pdf_page: number;
  printed_page: string | null;
  excerpt: string;
  filename: string;
  pdf_url: string;
  official_url?: string | null;
};

type ListedUnit = {
  name: string;
  code: string;
  category: string;
  years: number[];
  source_id: number;
  year?: number | null;
  original_value?: string | null;
};

type SearchResponse = {
  query: string;
  summary: string | null;
  insufficient_evidence: boolean;
  evidence: Evidence[];
  sources: SourceReference[];
  listed_units: ListedUnit[];
  warnings: string[];
  limitations: string[];
  interpretation: {
    intent: string;
    intent_label: string;
    technical_concept: string;
    entity_label: string | null;
    normalized_query: string;
    requires_confirmation: boolean;
    confirmation_reason: string | null;
    confirmed: boolean;
  } | null;
};

type CorpusStatus = {
  documents: number;
  pages: number;
  chunks: number;
  ocr_pages: number;
  blank_verified_pages: number;
  pending_review_pages: number;
  homologation_complete: boolean;
};

type FeedbackVerdict = "correct" | "incomplete" | "incorrect";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const years = Array.from({ length: 8 }, (_, index) => 2026 - index);

function SummaryWithCitations({
  text,
  sources,
}: {
  text: string;
  sources: SourceReference[];
}) {
  return text.split(/(\[\d+\])/g).map((part, index) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (!match) return <span key={`${part}-${index}`}>{part}</span>;
    const source = sources.find((item) => item.id === Number(match[1]));
    return source ? (
      <a key={`${part}-${index}`} href={`#source-${source.id}`} aria-label={`Ir para a fonte ${source.id}`}>
        {part}
      </a>
    ) : (
      <span key={`${part}-${index}`}>{part}</span>
    );
  });
}

type NumericSummaryRow = {
  label: string;
  code: string | null;
  year: number;
  value: string;
  sourceId: number | null;
};

function extractNumericRows(text: string): NumericSummaryRow[] {
  const rows: NumericSummaryRow[] = [];
  const institutionPattern =
    /([^.;]+?)\s+\(c[óo]digo\s+(\d+)\):\s*([\s\S]*?)(?=(?:[^.;]+?\s+\(c[óo]digo\s+\d+\):)|$)/gi;
  let institutionMatch: RegExpExecArray | null;

  while ((institutionMatch = institutionPattern.exec(text)) !== null) {
    const rawLabel = institutionMatch[1]
      .replace(/^S[ée]ries institucionais:\s*/i, "")
      .trim();
    const values = institutionMatch[3];
    const valuePattern = /(20\d{2}):\s*R\$\s*([\d.]+)(?:\s*\[(\d+)\])?/g;
    let valueMatch: RegExpExecArray | null;
    while ((valueMatch = valuePattern.exec(values)) !== null) {
      rows.push({
        label: rawLabel,
        code: institutionMatch[2],
        year: Number(valueMatch[1]),
        value: valueMatch[2],
        sourceId: valueMatch[3] ? Number(valueMatch[3]) : null,
      });
    }
  }

  if (rows.length > 0) return rows;

  const rankingPattern =
    /(20\d{2}):\s*(.+?)\s+\(c[óo]digo\s+(\d+)\),\s*R\$\s*([\d.]+)(?:\s*\[(\d+)\])?/gi;
  let rankingMatch: RegExpExecArray | null;
  while ((rankingMatch = rankingPattern.exec(text)) !== null) {
    rows.push({
      label: rankingMatch[2].trim(),
      code: rankingMatch[3],
      year: Number(rankingMatch[1]),
      value: rankingMatch[4],
      sourceId: rankingMatch[5] ? Number(rankingMatch[5]) : null,
    });
  }

  if (rows.length > 0) return rows;

  const singleInstitutionPattern =
    /(?:Na LOA de|Em)\s+(20\d{2}),?\s+(?:o total autorizado para\s+)?(.+?)\s+\(c[óo]digo\s+(\d+)\)\s+(?:foi de|:)\s+R\$\s*([\d.]+)(?:\s*\[(\d+)\])?/gi;
  let singleInstitutionMatch: RegExpExecArray | null;
  while (
    (singleInstitutionMatch = singleInstitutionPattern.exec(text)) !== null
  ) {
    rows.push({
      label: singleInstitutionMatch[2].trim(),
      code: singleInstitutionMatch[3],
      year: Number(singleInstitutionMatch[1]),
      value: singleInstitutionMatch[4],
      sourceId: singleInstitutionMatch[5]
        ? Number(singleInstitutionMatch[5])
        : null,
    });
  }

  if (rows.length > 0) return rows;

  const genericPattern = /(20\d{2}):\s*R\$\s*([\d.]+)(?:\s*\[(\d+)\])?/g;
  let genericMatch: RegExpExecArray | null;
  while ((genericMatch = genericPattern.exec(text)) !== null) {
    rows.push({
      label: "Tema consultado",
      code: null,
      year: Number(genericMatch[1]),
      value: genericMatch[2],
      sourceId: genericMatch[3] ? Number(genericMatch[3]) : null,
    });
  }
  return rows;
}

function NumericSummaryTable({
  text,
  sources,
}: {
  text: string;
  sources: SourceReference[];
}) {
  const rows = extractNumericRows(text);
  if (rows.length === 0) return null;

  const showInstitution =
    new Set(rows.map((row) => row.label)).size > 1 || rows[0].code !== null;
  return (
    <div className="numericTableWrapper">
      <table className="numericTable">
        <thead>
          <tr>
            {showInstitution && <th>Instituição ou tema</th>}
            <th>Ano</th>
            <th>Valor autorizado</th>
            <th>Fonte</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const source = row.sourceId
              ? sources.find((item) => item.id === row.sourceId)
              : null;
            return (
              <tr key={`${row.label}-${row.year}-${index}`}>
                {showInstitution && (
                  <td>
                    <strong>{row.label}</strong>
                    {row.code && <small>Código {row.code}</small>}
                  </td>
                )}
                <td>{row.year}</td>
                <td className="numericValue">R$ {row.value}</td>
                <td>
                  {source ? (
                    <a href={`#source-${source.id}`} aria-label={`Ir para a fonte ${source.id}`}>
                      [{source.id}] Ver fonte
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function UnitListTable({
  units,
  sources,
}: {
  units: ListedUnit[];
  sources: SourceReference[];
}) {
  if (units.length === 0) return null;
  const includesBudgetValues = units.some((unit) => unit.original_value);
  return (
    <div className="unitListWrapper">
      <table className="unitListTable">
        <thead>
          <tr>
            <th>Unidade orçamentária</th>
            <th>Código</th>
            <th>Classificação</th>
            <th>{includesBudgetValues ? "Ano" : "Período no acervo"}</th>
            {includesBudgetValues && <th>Valor autorizado</th>}
            <th>Fonte</th>
          </tr>
        </thead>
        <tbody>
          {units.map((unit) => {
            const source = sources.find((item) => item.id === unit.source_id);
            const firstYear = Math.min(...unit.years);
            const lastYear = Math.max(...unit.years);
            return (
              <tr key={`${unit.code}-${unit.year ?? "period"}`}>
                <td><strong>{unit.name}</strong></td>
                <td>{unit.code}</td>
                <td>{unit.category.replaceAll("_", " ")}</td>
                <td>
                  {unit.year ??
                    (firstYear === lastYear ? firstYear : `${firstYear}–${lastYear}`)}
                </td>
                {includesBudgetValues && (
                  <td className="numericValue">
                    {unit.original_value ? `R$ ${unit.original_value}` : "—"}
                  </td>
                )}
                <td>
                  {source ? <a href={`#source-${source.id}`}>[{source.id}] Ver fonte</a> : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [selectedYears, setSelectedYears] = useState<number[]>([]);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [permalink, setPermalink] = useState("");
  const [corpus, setCorpus] = useState<CorpusStatus | null>(null);
  const [isReviewer, setIsReviewer] = useState(false);
  const [feedbackVerdict, setFeedbackVerdict] = useState<FeedbackVerdict | null>(null);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [sendingFeedback, setSendingFeedback] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/corpus/status`)
      .then((response) => (response.ok ? response.json() : null))
      .then(setCorpus)
      .catch(() => setCorpus(null));
    fetch(`${API_URL}/me`)
      .then((response) => (response.ok ? response.json() : null))
      .then((user) => setIsReviewer(Boolean(user?.is_reviewer)))
      .catch(() => setIsReviewer(false));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await runSearch(true);
  }

  async function runSearch(interpretationConfirmed: boolean) {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          years: selectedYears,
          limit: 20,
          interpretation_confirmed: interpretationConfirmed,
        }),
      });
      if (!response.ok) throw new Error("Não foi possível consultar o acervo.");
      setResult(await response.json());
      setFeedbackVerdict(null);
      setFeedbackComment("");
      setFeedbackMessage("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha inesperada.");
    } finally {
      setLoading(false);
    }
  }

  function toggleYear(year: number) {
    setSelectedYears((current) =>
      current.includes(year) ? current.filter((item) => item !== year) : [...current, year],
    );
  }

  async function saveQuery() {
    const response = await fetch(`${API_URL}/saved-queries`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        search: {
          query,
          years: selectedYears,
          limit: 20,
          interpretation_confirmed: true,
        },
      }),
    });
    if (!response.ok) return setError("Não foi possível criar o link permanente.");
    const saved = await response.json();
    setPermalink(`${API_URL}/saved-queries/${saved.public_id}`);
  }

  async function exportPdf() {
    const response = await fetch(`${API_URL}/search/export.pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        years: selectedYears,
        limit: 20,
        interpretation_confirmed: true,
      }),
    });
    if (!response.ok) return setError("Não foi possível gerar o relatório.");
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "consulta-loa.pdf";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function sendFeedback() {
    if (!result || !feedbackVerdict) return;
    setSendingFeedback(true);
    setFeedbackMessage("");
    try {
      const response = await fetch(`${API_URL}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          years: selectedYears,
          response: result,
          verdict: feedbackVerdict,
          comment: feedbackComment,
        }),
      });
      if (!response.ok) throw new Error("Não foi possível registrar o feedback.");
      const saved = await response.json();
      setFeedbackMessage(saved.message);
    } catch (reason) {
      setFeedbackMessage(
        reason instanceof Error ? reason.message : "Falha inesperada ao registrar o feedback.",
      );
    } finally {
      setSendingFeedback(false);
    }
  }

  return (
    <main>
      <header className="masthead">
        <div>
          <p className="eyebrow">Redação · Fact-checking</p>
          <h1>LOA</h1>
        </div>
        <p className="status"><span /> Piloto restrito · Educação 2019–2026</p>
      </header>

      {corpus && !corpus.homologation_complete && (
        <aside className="homologation" role="status">
          <strong>Acervo em homologação</strong>
          <span>
            {corpus.pages.toLocaleString("pt-BR")} páginas indexadas ·{" "}
            {corpus.pending_review_pages.toLocaleString("pt-BR")} aguardando revisão
          </span>
          <span>Resultados pendentes não são liberados como evidência editorial.</span>
        </aside>
      )}

      <section className="hero">
        <p className="kicker">Pesquisa com evidências</p>
        <h2>Encontre o dado.<br />Confira a página.</h2>
        <p className="intro">
          Consulte a área federal de Educação nas Leis Orçamentárias Anuais sem perder
          o caminho até o documento original.
        </p>

        <section className="pilotCoverage" aria-label="Escopo do piloto">
          <div>
            <p className="eyebrow">Escopo do piloto</p>
            <p>
              Por enquanto, estão disponíveis para consultas e comparações somente os dados
              da LOA referentes à Educação.
            </p>
            <p>
              Saúde, Defesa, Cultura e os demais temas serão liberados mais adiante.
            </p>
            <p>
              O objetivo desta etapa é conhecer a experiência dos usuários e reunir relatos
              sobre como o aplicativo pode ser aperfeiçoado.
            </p>
          </div>
          {isReviewer && (
            <a className="feedbackReport" href={`${API_URL}/feedback/report.csv`}>
              Baixar relatório de feedback
            </a>
          )}
        </section>

        <form onSubmit={submit} className="search">
          <label htmlFor="query">O que você precisa verificar?</label>
          <div className="searchRow">
            <input
              id="query"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setResult(null);
                setPermalink("");
              }}
              placeholder="Ex.: Compare o orçamento da UFBA e da UFPR em 2024"
              minLength={2}
              required
            />
            <button disabled={loading}>{loading ? "Buscando…" : "Pesquisar"}</button>
          </div>
          <fieldset>
            <legend>Filtrar por exercício</legend>
            <div className="years">
              {years.map((year) => (
                <label key={year} className={selectedYears.includes(year) ? "active" : ""}>
                  <input
                    type="checkbox"
                    checked={selectedYears.includes(year)}
                    onChange={() => toggleYear(year)}
                  />
                  {year}
                </label>
              ))}
            </div>
            <p>Nenhum ano selecionado: a resposta considera todo o período de 2019 a 2026.</p>
          </fieldset>
        </form>
      </section>

      {error && <p className="error" role="alert">{error}</p>}

      {result && (
        <section className="results" aria-live="polite">
          <div className="resultHeader">
            <div>
              <p className="eyebrow">Resposta</p>
              <h3>Resposta resumida</h3>
            </div>
            <p className="separation">Cada referência leva à página do documento original.</p>
          </div>
          <div className="resultActions">
            <button type="button" onClick={saveQuery}>Criar link permanente</button>
            <button type="button" onClick={exportPdf}>Exportar PDF</button>
            {permalink && <a href={permalink} target="_blank" rel="noreferrer">{permalink}</a>}
          </div>

          {result.warnings.map((warning) => (
            <p className="warning" key={warning}>{warning}</p>
          ))}

          {result.summary && (
            <div className="summary answer">
              <p>
                <SummaryWithCitations text={result.summary} sources={result.sources} />
              </p>
              <NumericSummaryTable text={result.summary} sources={result.sources} />
            </div>
          )}

          <UnitListTable units={result.listed_units ?? []} sources={result.sources} />

          {result.limitations.length > 0 && (
            <aside className="limitations" aria-labelledby="limitations-title">
              <p className="eyebrow">Atenção editorial</p>
              <h3 id="limitations-title">Limitações e cobertura</h3>
              <ul>
                {result.limitations.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            </aside>
          )}

          {result.sources.length > 0 && (
            <section className="sourceReferences" aria-labelledby="sources-title">
              <h3 id="sources-title">Fontes citadas</h3>
              {result.sources.map((source) => (
                <article id={`source-${source.id}`} className="sourceCard" key={source.id}>
                  <div className="sourceHeading">
                    <span className="sourceNumber">[{source.id}]</span>
                    <div>
                      <strong>{source.document} ({source.year})</strong>
                      <small>
                        Página PDF {source.pdf_page}
                        {source.printed_page ? ` · página impressa ${source.printed_page}` : ""}
                      </small>
                    </div>
                    <div className="sourceLinks">
                      <a href={`${API_URL}${source.pdf_url}`} target="_blank" rel="noreferrer">
                        Abrir PDF na página citada ↗
                      </a>
                    </div>
                  </div>
                  <details>
                    <summary>Ver trecho original</summary>
                    <blockquote>{source.excerpt}</blockquote>
                  </details>
                </article>
              ))}
            </section>
          )}

          <section className="feedbackCard" aria-labelledby="feedback-title">
            <p className="eyebrow">Validação humana</p>
            <h3 id="feedback-title">Como você avalia esta resposta?</h3>
            <div className="feedbackChoices">
              {([
                ["correct", "Correta"],
                ["incomplete", "Incompleta"],
                ["incorrect", "Incorreta"],
              ] as [FeedbackVerdict, string][]).map(([value, label]) => (
                <button
                  className={feedbackVerdict === value ? "selected" : ""}
                  key={value}
                  onClick={() => setFeedbackVerdict(value)}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
            <label htmlFor="feedback-comment">O que faltou ou precisa ser corrigido?</label>
            <textarea
              id="feedback-comment"
              maxLength={4000}
              onChange={(event) => setFeedbackComment(event.target.value)}
              placeholder="Descreva o problema ou a sugestão."
              value={feedbackComment}
            />
            <button
              className="feedbackSubmit"
              disabled={!feedbackVerdict || sendingFeedback}
              onClick={sendFeedback}
              type="button"
            >
              {sendingFeedback ? "Registrando…" : "Registrar para análise"}
            </button>
            {feedbackMessage && (
              <p className="feedbackMessage" role="status">{feedbackMessage}</p>
            )}
          </section>
        </section>
      )}

      <footer>
        <p>Fonte exclusiva nesta versão: documentos oficiais indexados no acervo local.</p>
        <p>A conclusão editorial pertence ao jornalista.</p>
      </footer>
    </main>
  );
}
