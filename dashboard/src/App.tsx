import { useEffect, useState } from "react";

type Conversation = {
  id: number;
  created_at: string;
  question: string;
  area: string | null;
  psi: number | null;
  answer: string;
  tools_used: string[];
  route: string | null;
  flagged: boolean;
};

function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState<string | null>(null);

  // NEW: which conversation is clicked. null = nothing selected yet.
  const [selected, setSelected] = useState<Conversation | null>(null);

  useEffect(() => {
    fetch("/conversations")
      .then((res) => res.json())
      .then((data: Conversation[]) => setConversations(data))
      .catch((err) => setError(String(err)));
  }, []);

  // NEW: called when you click the Flag/Unflag button
  async function toggleFlag(id: number) {
    // `...${id}...` with backticks = Python f-string. method: "POST" = send a POST, not a GET
    const res = await fetch(`/conversations/${id}/flag`, { method: "POST" });
    const updated: Conversation = await res.json();   // the API sends back the updated row

    // Swap the old row for the updated one in the list:
    // for each c, if it's the one we flagged, use `updated`, otherwise keep c
    setConversations((list) => list.map((c) => (c.id === updated.id ? updated : c)));
    setSelected(updated);
  }

  if (error) return <p>Error: {error}</p>;
    // ===== STATS (worked out from the list we already have) =====
  const total = conversations.length;   // how many rows

  // .filter keeps only the items where the test is true, like Python [c for c in list if c.flagged]
  const flaggedCount = conversations.filter((c) => c.flagged).length;

  // Only rows that have a PSI (skip nulls)
  const withPsi = conversations.filter((c) => c.psi !== null);

  // .reduce adds them up, like Python sum(c.psi for c in withPsi)
  //   sum starts at 0, then for each c: sum = sum + c.psi
  const psiTotal = withPsi.reduce((sum, c) => sum + (c.psi ?? 0), 0);

  // Avoid dividing by 0 when there are no rows yet
  const avgPsi = withPsi.length === 0 ? null : Math.round(psiTotal / withPsi.length);

  return (
    <div>
      <h1>Haze Agent Conversations</h1>
      <p>
        Total: {total} | Flagged: {flaggedCount} | Avg PSI: {avgPsi ?? "-"}
      </p>
      <ul>
        {conversations.map((c) => (
          // NEW: onClick = when this row is clicked, make it the selected one
          <li
            key={c.id}
            // If this row is already selected, deselect it (null). Otherwise select it.
            onClick={() => setSelected(selected?.id === c.id ? null : c)}
            style={{ cursor: "pointer" }}
          >
            {c.flagged ? "FLAGGED - " : ""}
            {c.question} ({c.area}, PSI {c.psi})
          </li>
        ))}
      </ul>

      {/* NEW: detail panel.
          "selected && (...)" = only show this part if something is selected */}
      {selected && (
        <div>
          <h2>{selected.question}</h2>

          {/* Turn the UTC time into Singapore local time */}
          <p>{new Date(selected.created_at).toLocaleString("en-SG")}</p>

          {/* ?? "-" = if the value is null, show "-" instead */}
          <p>
            Area: {selected.area ?? "-"} | PSI: {selected.psi ?? "-"} | Route: {selected.route ?? "-"}
          </p>

          {/* .join(", ") turns ["get_psi","search_advisories"] into "get_psi, search_advisories" */}
          <p>Tools: {selected.tools_used.join(", ")}</p>

          {/* pre-wrap keeps the answer's line breaks */}
          <p style={{ whiteSpace: "pre-wrap" }}>{selected.answer}</p>

          <button onClick={() => toggleFlag(selected.id)}>
            {selected.flagged ? "Unflag" : "Flag"}
          </button>
        </div>
      )}
    </div>
  );
}

export default App;