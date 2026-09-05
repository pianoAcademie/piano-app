// Test-only full-screen fixture; mounted temporarily by teacher-mobile-browser.mjs.
import LearningCard from "../../components/teacher-ui/learning-card";
import { AttendanceDialog, StudentPager, AttendanceButton } from "../../components/teacher-ui/attendance-workspace";
import styles from "../../components/teacher-ui/teacher-mobile.module.css";
import PageHeaderMobile from "../../components/teacher-ui/page-header-mobile";
import MonthDayCard from "../../components/planning/month-day-card";
export default function Page({searchParams}:{searchParams:{closed?:string}}) {
  const ids=["11111111-1111-4111-8111-111111111111","22222222-2222-4222-8222-222222222222"];
  const catalog=[{product_id:"book",title:"Partition degré 7",pieces:["Printemps — Vivaldi","Menuet — Bach","Petite valse"].map((title,i)=>({id:String(i),title,position:i,video_url:null}))}];
  const events=[{id:"course",title:"Cours de piano collectif en présentiel",start_at_utc:"2026-09-07T13:00:00Z",end_at_utc:"2026-09-07T14:00:00Z",timezone:"Europe/Paris",capacity_max:6,booked_count:5,teacher_display_name:"Professeur de démonstration",location_label:"Rue de Richelieu",type_label:"Cours collectif enfants",status_label:"Planifié",status:"SCHEDULED"}];
  return <main className={`page prof-page teacher-shell ${styles.portal}`}>
    <PageHeaderMobile title="Professeur de démonstration" subtitle="professeur@example.invalid" statusLabel="Actif" trailing={<a className="mode-link teacher-admin-switch-link" href="#">Retour administration</a>} />
    <section className="card teacher-planning-card"><h2>Planning</h2>
      <form className="grid cols-4 teacher-planning-controls"><label>Vue<select defaultValue="day"><option value="day">Jour</option></select></label><label>Date<input type="date" defaultValue="2026-09-07" /></label><div className="teacher-planning-controls-actions"><a href="#">Aujourd’hui</a></div><div className="teacher-planning-controls-arrows"><a className="mode-link" href="#">←</a><a className="mode-link" href="#">→</a></div></form>
      <div className="agenda-grid coach-agenda-grid agenda-grid-week">{["Lundi 7 septembre","Mardi 8 septembre"].map(day=><MonthDayCard key={day} dayLabel={day} events={events} isToday={false} expanded dayDetailsHref="#" openSessionHref={()=>"#"}/>)}</div>
    </section>
    {!searchParams.closed && <AttendanceDialog closeHref="/mobile-qa?closed=1"><article className="modal-panel session-attendance-modal-v2 teacher-attendance-modal">
      <header className="teacher-attendance-header"><div className="teacher-attendance-header-main"><h2 className="modal-title">Présences</h2><p>7 sept. 2026, 15:00–16:00 · Rue de Richelieu</p></div><div className="teacher-attendance-header-meta"><a className="modal-close-x" href="/mobile-qa?closed=1" aria-label="Fermer">×</a></div></header>
      <div className="teacher-attendance-body"><section className="teacher-attendance-primary"><StudentPager sessionId="qa" students={ids.map((id,i)=>({id,name:["Élève A","Élève B"][i]}))}>
        {ids.map((id,i)=><article className="teacher-attendance-row-card" key={id}><strong>{["Élève A","Élève B"][i]}</strong><div className="teacher-attendance-segment-grid">{["Présent","Excusé","Non excusé"].map(label=><form key={label}><input type="hidden" name="attendance_status" value="ATTENDED"/><AttendanceButton className="teacher-attendance-btn">{label}</AttendanceButton></form>)}</div>
          <details className="teacher-student-note"><summary>Note élève</summary><textarea aria-label="Note élève" defaultValue="" /></details>
          <LearningCard studentId={id} studentName={["Élève A","Élève B"][i]} sessionId={ids[0]} catalog={catalog} initial={{revision:0,state:{product_id:"book",books:{book:{current_piece_id:i===0?"1":null,completed:false,pieces:{}}}}}}/>
        </article>)}
      </StudentPager></section><details className="teacher-course-tools"><summary>Notes et informations du groupe</summary><aside className="teacher-attendance-secondary"><details className="teacher-attendance-accordion"><summary>Note générale du cours</summary><div className="teacher-attendance-accordion-body"><textarea aria-label="Note générale du cours"/></div></details><details className="teacher-attendance-accordion"><summary>Messages envoyés</summary></details></aside></details></div>
      <footer className="teacher-attendance-footer"><div className="row"><span>À saisir : 2</span><a className="mode-link" href="/mobile-qa?closed=1">Retour au planning</a></div></footer>
    </article></AttendanceDialog>}
  </main>;
}
