"use client";

import { useId, useMemo, useState, type ReactNode } from "react";

import type { AdminExternalContentCourseOut } from "../lib/types";
import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type ActivityModalTabsProps = {
  activityLabel?: string;
  contentLabel?: string;
  activityContent: ReactNode;
  contentContent: ReactNode;
  language?: UiLanguage | string;
};

export function ActivityModalTabs({
  activityLabel,
  contentLabel,
  activityContent,
  contentContent,
  language: languageProp = "fr",
}: ActivityModalTabsProps) {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const resolvedActivityLabel = activityLabel ?? t("admin.activity_content.tab_activity");
  const resolvedContentLabel = contentLabel ?? t("admin.activity_content.tab_content");
  const [activeTab, setActiveTab] = useState<"activity" | "content">("activity");
  const tabsId = useId().replace(/:/g, "");
  const activityPanelId = `${tabsId}-activity-panel`;
  const contentPanelId = `${tabsId}-content-panel`;

  return (
    <div className="activity-modal-tabs-shell">
      <div className="activity-modal-tablist" role="tablist" aria-label={t("admin.activity_content.tabs_aria")}>
        <button
          type="button"
          role="tab"
          id={`${tabsId}-activity-tab`}
          aria-selected={activeTab === "activity"}
          aria-controls={activityPanelId}
          className={`activity-modal-tab${activeTab === "activity" ? " is-active" : ""}`}
          onClick={() => setActiveTab("activity")}
        >
          {resolvedActivityLabel}
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
          {resolvedContentLabel}
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
  language?: UiLanguage | string;
};

export default function ActivityContentAssignmentsPicker({
  courses,
  defaultSelectedCourseIds,
  language: languageProp = "fr",
}: ActivityContentAssignmentsPickerProps) {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const [query, setQuery] = useState("");
  const [selectedCourseIds, setSelectedCourseIds] = useState(() => new Set(defaultSelectedCourseIds));

  const normalizedQuery = query.trim().toLowerCase();
  const searchLevelLabel = t("admin.activity_content.level_label").toLowerCase();
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
            course.level_code ? `${searchLevelLabel} ${course.level_code}` : "",
            course.level_code ? `niveau ${course.level_code}` : "",
            course.level_code ? `level ${course.level_code}` : "",
          ]
            .join(" ")
            .toLowerCase();
          return haystack.includes(normalizedQuery);
        })
        .map((course) => course.id),
    );
  }, [courses, normalizedQuery, searchLevelLabel]);

  const visibleCount = visibleCourseIds.size;
  const selectedCount = selectedCourseIds.size;

  if (courses.length === 0) {
    return (
      <div className="activity-content-empty">
        <p className="muted">{t("admin.activity_content.empty_title")}</p>
        <p className="muted">{t("admin.activity_content.empty_help")}</p>
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
          {t("admin.activity_content.search_label")}
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("admin.activity_content.search_placeholder")}
          />
        </label>
        <div className="activity-content-toolbar-stats">
          <span className="activity-content-stat">
            {t("admin.activity_content.selection_count", { count: selectedCount })}
          </span>
          <span className="activity-content-stat">
            {t("admin.activity_content.result_count", { count: visibleCount })}
          </span>
        </div>
      </div>

      {visibleCount === 0 ? (
        <div className="activity-content-no-results">
          <strong>{t("admin.activity_content.no_results_title")}</strong>
          <small>{t("admin.activity_content.no_results_help")}</small>
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
                  {course.level_code
                    ? t("admin.activity_content.level_value", { level: course.level_code })
                    : t("admin.activity_content.level_missing")} · {t("admin.activity_content.sections_count", { count: course.sections_count })}
                  {" · "}
                  {t("admin.activity_content.lessons_count", { count: course.lessons_count })}
                </small>
                {course.summary ? <small>{course.summary}</small> : null}
              </span>
              <span className={`status-pill ${course.status === "PUBLISHED" ? "status-ok" : "status-warn"}`}>
                {course.status === "PUBLISHED" ? t("admin.activity_content.published") : course.status}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
