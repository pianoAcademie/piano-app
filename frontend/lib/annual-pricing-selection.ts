export type Audience = "CHILD" | "TEEN" | "ADULT";
export type StudentOption = { id: string; label: string; kind?: "CLIENT" | "PROSPECT"; audiences?: Audience[] };
export type CourseOption = { id: string; title: string; quantity: string; audiences?: Audience[] };

export function allowedAudiences(student: StudentOption | undefined, lines: CourseOption[]): Audience[] {
  if (!student) return [];
  return (student.audiences || ["CHILD", "TEEN"]).filter(a => lines.every(l => !l.audiences || l.audiences.includes(a)));
}

export function initialStudent(students: StudentOption[], reviewId?: string): string {
  if (reviewId && students.some(s => s.id === reviewId)) return reviewId;
  return students.length === 1 ? students[0].id : "";
}
