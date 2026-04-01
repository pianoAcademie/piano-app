"use client";

import { useId, useMemo, useState, type ReactNode } from "react";

import type { AdminExternalContentCourseOut } from "../lib/types";

type ActivityModalTabsProps = {
  activityLabel?: string;
  contentLabel?: string;
  activityContent: ReactNode;
  contentContent: ReactNode;
};

export function ActivityModalTabs({
  activityLabel = "Activite",
  contentLabel = "Contenu en ligne",
  activityContent,
  contentContent,
}: ActivityModalTabsProps) {
  const [activeTab, setActiveTab] = useState<"activity" | "content">("activity");
  const tabsId = useId().replace(/:/g, "");
  const activityPanelId = `${tabsId}-activity-panel`;
  const contentPanelId = `${tabsId}-content-panel`;

  return (
    <div className="activity-modal-tabs-shell">
      <div className="activity-modal-tablist" role="tablist" aria-label="Edition de l activite">
        <button
          type="button"
          role="tab"
          id={`${tabsId}-activity-tab`}
          aria-selected={activeTab === "activity"}
          aria-controls={activityPanelId}
          className={`activity-modal-tab${activeTab === "activity" ? " is-active" : ""}`}
          onClick={() => setActiveTab("activity")}
        >
          {activityLabel}
        </button>
        <button
          type="button"
          role="tab"
          id={`${tabsId}-content-tab`}
          aria-selected={activeTab === "content"}
          aria-controls={contentPanelId}
          className={`activity-modal-tab${activeTab === "content" ? " is-active" : ""}`}
          onClick={() => setActiveTab("content")}
        >
          {contentLabel}
        </button>
      </div>

      <div
        id={activityPanelId}
        role="tabpanel"
        aria-labelledby={`${tabsId}-activity-tab`}
        className={`activity-modal-tabpanel${activeTab === "activity" ? " is-active" : ""}`}
        hidden={activeTab !== "activity"}
      >
        {activityContent}
      </div>

      <div
        id={contentPanelId}
        role="tabpanel"
        aria-labelledby={`${tabsId}-content-tab`}
        className={`activity-modal-tabpanel${activeTab === "content" ? " is-active" : ""}`}
        hidden={activeTab !== "content"}
      >
        {contentContent}
      </div>
    </div>
  );
}

type ActivityContentAssignmentsPickerProps = {
  courses: AdminExternalContentCourseOut[];
  defaultSelectedCourseIds: string[];
};

export default function ActivityContentAssignmentsPicker({
  courses,
  defaultSelectedCourseIds,
}: ActivityContentAssignmentsPickerProps) {
  const [query, setQuery] = useState("");
  const [selectedCourseIds, setSelectedCourseIds] = useState(() => new Set(defaultSelectedCourseIds));

  const normalizedQuery = query.trim().toLowerCase();
  const visibleCourseIds = useMemo(() => {
    if (!normalizedQuery) {
      return new Set(courses.map((course) => course.id));
    }
    return new Set(
      courses
        .filter((course) => {
          const haystack = [
            course.title,
            course.summary ?? "",
            course.level_code ? `niveau ${course.level_code}` : "",
          ]
            .join(" ")
            .toLowerCase();
          return haystack.includes(normalizedQuery);
        })
        .map((course) => course.id),
    );
  }, [courses, normalizedQuery]);

  const visibleCount = visibleCourseIds.size;
  const selectedCount = selectedCourseIds.size;

  if (courses.length === 0) {
    return (
      <div className="activity-content-empty">
        <p className="muted">Aucun contenu synchronise pour le moment.</p>
        <p className="muted">
          Synchronisez d abord le catalogue WordPress / LearnDash, puis revenez ici pour rattacher les cours eleves.
        </p>
      </div>
    );
  }

  function toggleCourse(courseId: string, checked: boolean) {
    setSelectedCourseIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(courseId);
      } else {
        next.delete(courseId);
      }
      return next;
    });
  }

  return (
    <div className="activity-content-picker">
      <div className="activity-content-toolbar">
        <label className="activity-content-search">
          Rechercher un cours
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Titre du cours LearnDash"
          />
        </label>
        <div className="activity-content-toolbar-stats">
          <span className="activity-content-stat">
            {selectedCount} selection{selectedCount > 1 ? "s" : ""}
          </span>
          <span className="activity-content-stat">
            {visibleCount} resultat{visibleCount > 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {visibleCount === 0 ? (
        <div className="activity-content-no-results">
          <strong>Aucun cours ne correspond a cette recherche.</strong>
          <small>Essayez un autre titre, niveau ou mot cle.</small>
        </div>
      ) : null}

      <div className="activity-content-grid">
        {courses.map((course) => {
          const isVisible = visibleCourseIds.has(course.id);
          const isSelected = selectedCourseIds.has(course.id);
          return (
            <label
              key={course.id}
              className={`activity-content-card${isSelected ? " is-selected" : ""}${isVisible ? "" : " is-hidden"}`}
            >
              <span className="activity-planning-checkbox">
                <input
                  type="checkbox"
                  name="content_course_ids"
                  value={course.id}
                  checked={isSelected}
                  onChange={(event) => toggleCourse(course.id, event.target.checked)}
                />
              </span>
              <span className="activity-content-copy">
                <strong>{course.title}</strong>
                <small>
                  {course.level_code ? `Niveau ${course.level_code}` : "Niveau non precise"} · {course.sections_count} section(s)
                  {" · "}
                  {course.lessons_count} lecon(s)
                </small>
                {course.summary ? <small>{course.summary}</small> : null}
              </span>
              <span className={`status-pill ${course.status === "PUBLISHED" ? "status-ok" : "status-warn"}`}>
                {course.status === "PUBLISHED" ? "Publie" : course.status}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
