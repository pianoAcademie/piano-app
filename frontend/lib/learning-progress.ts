export type PieceStatus = "UNKNOWN" | "REVIEW" | "COMPLETED";
export type LearningBook = {
  note?: string;
  current_piece_id: string | null;
  completed: boolean;
  pieces: Record<string, { status: PieceStatus; source: string; completed_at: string | null }>;
};
export type LearningSnapshot = {
  revision: number;
  state: { product_id: string | null; books: Record<string, LearningBook> };
  undo_event_id?: string | null;
  history?: Array<{ id: string; action: string; at: string; session_id: string; actor_id: string; actor_name: string; product_id: string | null; piece_id: string | null }>;
};
export type LearningCommand = {
  revision: number;
  session_id: string;
  action: "CORRECT" | "HISTORY" | "CONTINUE" | "COMPLETE_PIECE" | "COMPLETE_BOOK" | "NEXT_BOOK" | "UNDO";
  product_id?: string | null;
  piece_id?: string | null;
  statuses?: Record<string, PieceStatus>;
  undo_event_id?: string | null;
  note?: string;
};
