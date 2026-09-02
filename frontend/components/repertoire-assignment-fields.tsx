"use client";

import { useMemo, useState } from "react";

import type { RepertoirePartitionOut } from "../lib/types";

type Props = {
  catalog: RepertoirePartitionOut[];
  initialProductId: string | null;
  initialPieceId: string | null;
};

export default function RepertoireAssignmentFields({ catalog, initialProductId, initialPieceId }: Props) {
  const [productId, setProductId] = useState(initialProductId ?? "");
  const [pieceId, setPieceId] = useState(initialPieceId ?? "");
  const partition = useMemo(
    () => catalog.find((candidate) => candidate.product_id === productId) ?? null,
    [catalog, productId],
  );
  const pieces = partition?.pieces ?? [];
  const selectedPiece = pieces.find((piece) => piece.id === pieceId) ?? null;

  return (
    <>
      <label>
        Degré / partition
        <select
          name="product_id"
          value={productId}
          required
          onChange={(event) => {
            setProductId(event.target.value);
            setPieceId("");
          }}
        >
          <option value="">Choisir une partition</option>
          {catalog.map((candidate) => (
            <option key={candidate.product_id} value={candidate.product_id}>{candidate.title}</option>
          ))}
        </select>
      </label>
      <label>
        Morceau travaillé
        <select name="current_piece_id" value={pieceId} onChange={(event) => setPieceId(event.target.value)}>
          <option value="">À définir</option>
          {pieces.map((piece) => (
            <option key={piece.id} value={piece.id}>{piece.title}</option>
          ))}
        </select>
      </label>
      {partition && pieces.length === 0 ? (
        <small className="muted">Aucun morceau n’est encore enregistré pour cette partition.</small>
      ) : null}
      {selectedPiece?.video_url ? (
        <a href={selectedPiece.video_url} target="_blank" rel="noreferrer">Voir la vidéo du morceau ↗</a>
      ) : null}
    </>
  );
}
