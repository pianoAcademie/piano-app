from __future__ import annotations

import base64
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from html import escape, unescape as html_unescape
from html.parser import HTMLParser
import io
import json
import logging
import re
from typing import Any
import unicodedata
from uuid import UUID
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session
from xhtml2pdf import pisa

from app.models.ops import AppSetting, LegalEntity
from app.models.product_catalog import CatalogKit, CatalogKitItem, CatalogProduct
from app.models.catalog import CourseSession, CourseType, Location, SessionStatus
from app.models.family import ClientFamilyLink
from app.models.quote import Prospect, Quote, QuoteLine, QuoteTemplate, QuoteTemplateVersion, SolfegeLevelRule, TermsTemplateVersion
from app.models.typeform_intake import TypeformIntake
from app.models.user import ClientKind, User
from app.services.i18n import normalize_language
from app.services.quotes.calendar_engine import CalendarGenerationInput, generate_calendar_snapshot


AUDIENCE_ADMIN_PREVIEW = "admin_preview"
AUDIENCE_PUBLIC_PAGE = "public_page"
AUDIENCE_CLIENT_PDF = "client_pdf"
DEFAULT_AUDIENCE = AUDIENCE_CLIENT_PDF
ACCOUNT_LOGO_SETTING_KEY = "config_account_logo_data_url"
QUOTE_SCHOOL_CALENDARS_SETTING_KEY = "quote_school_calendars_v1"
CARD_4X_FEES_PAYMENT_METHOD = "CARD_4X_FEES"
CARD_4X_FEES_PAYMENT_INSTRUCTION = (
    "Le paiement par carte bancaire en 4 fois est géré par notre partenaire Oney.\n"
    "Votre dossier sera donc soumis à Oney, qui pourra l’accepter ou le refuser.\n"
    "Une partie des frais liés au paiement échelonné est prise en charge par Piano Académie. "
    "L’autre partie sera directement intégrée à votre échéancier par Oney."
)
logger = logging.getLogger(__name__)
DAY_LABELS_FR = {
    0: "Lundi",
    1: "Mardi",
    2: "Mercredi",
    3: "Jeudi",
    4: "Vendredi",
    5: "Samedi",
    6: "Dimanche",
}
CSS_VAR_RE = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)\s*(?:,\s*([^)]+?)\s*)?\)")
CSS_VAR_DEFAULTS: dict[str, str] = {
    "--line-soft": "#d6d9de",
    "--line": "#cfd3da",
    "--ink": "#1f1f1f",
    "--text": "#1f1f1f",
    "--text-muted": "#6b7280",
    "--muted": "#6b7280",
    "--bg": "#ffffff",
    "--panel": "#ffffff",
    "--panel-2": "#f9fafb",
    "--accent": "#c9872a",
    "--accent-ink": "#ffffff",
}

QUOTE_DOC_TEXT = {
    "fr": {
        "schedule_due_invoice": "à réception de votre facture",
        "schedule_due_validation": "à la validation du devis, avant votre 1er cours",
        "schedule_due_before_first_course": "avant le démarrage du 1er cours",
        "payment_method_bank": "virement bancaire",
        "payment_method_check_one": "cheque",
        "payment_method_check_many": "cheques",
        "payment_method_card": "reglement par carte bancaire",
        "payment_method_generic": "reglement",
        "check_instruction_order": "Les chèques doivent être émis à l’ordre de {payee}.",
        "check_instruction_send": "Merci de signer vos chèques et de les envoyer à l’adresse suivante : Piano Academie, 1 rue de Richelieu, 75001 PARIS.",
        "check_instruction_split_send_all": "En cas de règlement en plusieurs fois par chèque, l’ensemble des chèques doit être envoyé avant le démarrage des cours.",
        "check_instruction_deposit_card": "L’acompte de {deposit_amount} doit être réglé par carte bancaire dès validation du devis. Une facture d’acompte vous sera envoyée avec le lien de paiement.",
        "deposit_bank_line_1": "Afin de bloquer définitivement le créneau, un acompte de {deposit_amount} devra être réglé par virement bancaire dès validation du devis.",
        "deposit_bank_line_2": "Une facture d’acompte sera émise après validation du devis.",
        "deposit_bank_line_3": "Le solde de {remaining_amount} devra être réglé par virement bancaire à réception de la facture de solde, avant le démarrage des cours.",
        "deposit_card_line_1": "Paiement d’un acompte de {deposit_amount} dès validation du devis, afin de bloquer le créneau.",
        "deposit_card_line_2": "Une facture d’acompte sera envoyée et devra être réglée rapidement après validation en ligne.",
        "deposit_card_line_3": "Le solde de {remaining_amount} devra être réglé par carte bancaire à réception de la facture correspondante, avant le démarrage des cours.",
        "payment_balance_bank_invoice": "reglement du solde de {amount} par virement bancaire à réception de votre facture, avant le démarrage des cours",
        "payment_sentence_generic": "{method_subject} de {amount} à regler {due_label}",
        "payment_deposit_then": "Après paiement de l’acompte de {deposit_amount} {currency} par carte bancaire, {remaining_sentence}.",
        "payment_installments_after_deposit": "Après paiement de l’acompte de {deposit_amount} {currency} par carte bancaire, le solde est à régler en {count} échéances selon le détail ci-dessous.",
        "payment_deposit_invoice_without_schedule": "Une facture d’acompte de {deposit_amount} sera dans un premier temps envoyée pour bloquer votre créneau.",
        "payment_installments": "Le règlement est prévu en {count} échéances selon le détail ci-dessous.",
        "payment_deposit_only": "L’acompte de {deposit_amount} {currency} est à régler par carte bancaire dès validation du devis afin de bloquer le créneau.",
        "payment_not_scheduled": "Paiement non planifié",
        "quote_status_approved": "Approuvé le",
        "quote_status_validity": "Validité",
        "quote_status_valid_until": "Valable jusqu’au {date}",
        "calendar_month_1": "Janvier",
        "calendar_month_2": "Février",
        "calendar_month_3": "Mars",
        "calendar_month_4": "Avril",
        "calendar_month_5": "Mai",
        "calendar_month_6": "Juin",
        "calendar_month_7": "Juillet",
        "calendar_month_8": "Août",
        "calendar_month_9": "Septembre",
        "calendar_month_10": "Octobre",
        "calendar_month_11": "Novembre",
        "calendar_month_12": "Décembre",
        "calendar_heading_default": "Cours {index}",
        "calendar_no_sessions": "Aucune séance planifiée",
        "calendar_summary": "{session_count} {session_label} pour {activity_count} {activity_label}",
        "calendar_session_singular": "séance planifiée",
        "calendar_session_plural": "séances planifiées",
        "calendar_activity_singular": "activité",
        "calendar_activity_plural": "activités",
        "weekday_0": "Lundi",
        "weekday_1": "Mardi",
        "weekday_2": "Mercredi",
        "weekday_3": "Jeudi",
        "weekday_4": "Vendredi",
        "weekday_5": "Samedi",
        "weekday_6": "Dimanche",
        "modality_default": "Cours",
        "modality_online": "En ligne",
        "modality_onsite": "Présentiel",
        "modality_hybrid": "Hybride",
        "slot_mode_online": "Mode : cours en ligne",
        "slot_mode_onsite": "Mode : cours en présentiel",
        "slot_mode_hybrid": "Mode : cours en présentiel ou en ligne",
        "planning_type_activity": "Type activité",
        "planning_activity": "Activité",
        "planning_location": "Lieu",
        "planning_day": "Jour",
        "planning_time": "Horaire",
        "planning_duration": "Durée",
        "planning_empty": "Aucun bloc planning.",
        "schedule_label": "Échéance",
        "schedule_amount": "Montant",
        "schedule_when": "Dépôt en banque",
        "schedule_type": "Type",
        "schedule_empty": "Aucun échéancier.",
        "calendar_date": "Date",
        "calendar_start": "Début",
        "calendar_end": "Fin",
        "calendar_modality": "Modalité",
        "calendar_empty": "Aucun cours planifié.",
        "section_courses_options": "Cours et options choisis",
        "section_services": "Cours inclus dans le devis",
        "section_adjustments": "Remises appliquées",
        "section_products": "Matériel pédagogique",
        "section_kits": "Frais et services inclus dans l’inscription",
        "section_other_fees": "Autres frais",
        "section_schedule": "Échéancier de paiement",
        "section_calendar": "Calendrier prévisionnel des cours",
        "cover_title": "Votre devis d’inscription",
        "cover_quote": "Devis",
        "cover_school_year": "Année scolaire",
        "cover_student": "Élève",
        "identity_title": "Informations de l’élève et du responsable",
        "identity_child": "Élève",
        "identity_birth_date": "Date de naissance",
        "identity_adult_contact": "Adulte responsable",
        "identity_adult_contact_email": "Email adulte responsable",
        "identity_adult_contact_phone": "Téléphone adulte responsable",
        "identity_adult_contact_address": "Adresse adulte responsable",
        "identity_email": "Email",
        "identity_phone": "Téléphone",
        "identity_address": "Adresse",
        "table_quantity": "Quantité",
        "table_vat": "TVA",
        "table_unit_price_ttc": "PU TTC",
        "table_total_ttc": "Montant TTC",
        "table_material": "Matériel",
        "table_kit": "Kit",
        "kit_includes": "Comprend",
        "table_type": "Type",
        "table_title": "Intitulé",
        "table_category": "Catégorie",
        "empty_activity": "Aucune activité.",
        "empty_material": "Aucun matériel.",
        "empty_kit": "Aucun kit.",
        "empty_adjustment": "Aucune remise ni supplément.",
        "empty_other_fee": "Aucun autre frais.",
        "fee_discount": "Remise",
        "fee_surcharge": "Supplément",
        "fee_service": "Service",
        "fee_material": "Matériel",
        "fee_kit": "Kit",
        "financial_title": "Montant total du devis",
        "financial_total_before_adjustment": "Total TTC avant ajustement",
        "financial_adjustment": "Ajustement",
        "financial_impact": "Impact",
        "financial_adjustment_date": "Date ajustement",
        "financial_total_ht_invoice": "Total HT facture",
        "financial_vat_invoice": "TVA facture ({rate} %)",
        "financial_total_ttc_quote": "Total TTC du devis",
        "financial_total_ht": "Total HT",
        "financial_vat": "TVA ({rate} %)",
        "payment_title": "Règlement et échéancier",
        "payment_method": "Mode de paiement",
        "options_title": "Vos options",
        "calendar_title": "Calendrier prévisionnel des cours",
        "calendar_overview": "Vue d’ensemble du calendrier : {summary}",
        "calendar_course_place": "Cours / lieu",
        "calendar_course_count": "Nombre de cours",
        "calendar_course_count_value": "{count} cours",
        "semester_1": "1er semestre",
        "semester_2": "2e semestre",
        "calendar_course_dates": "Dates de cours",
        "calendar_no_session_short": "Aucune séance",
        "terms_title": "Conditions d’inscription 2026–2027",
        "terms_version_unspecified": "Version non précisée",
        "payment_method_unspecified": "Paiement non précisé",
        "compact_notice_one": "1 échéance : {due_label}",
        "compact_notice_many": "Paiement en {count} échéances. Le détail des échéances est communiqué séparément.",
        "table_semester": "Semestre",
        "table_month": "Mois",
        "terms_empty": "Aucune condition générale.",
        "terms_snapshot_empty": "Aucune CGV snapshotée.",
        "quote_recipient": "Destinataire",
        "prospect_type": "Type de prospect",
        "prospect_type_child": "Enfant",
        "prospect_type_adult": "Adulte",
        "generated_at": "Document généré le",
        "financial_adjustment_credit": "Avoir",
        "financial_adjustment_debt": "Dette",
        "financial_adjustment_none": "Aucun",
        "financial_adjustment_credit_impact": "Déduit du total facturé",
        "financial_adjustment_debt_impact": "Ajouté au total facturé",
        "financial_adjustment_none_html": "Aucun avoir ou dette appliqué.",
        "financial_label": "Libellé",
        "financial_deposit": "Acompte préinscription",
        "financial_remaining_after_deposit": "Reste à payer après acompte",
        "financial_remaining_ht": "Total HT restant",
        "financial_remaining_vat": "TVA restante ({rate} %)",
        "deposit_section_title": "Acompte préinscription",
        "deposit_balance_bank_due": "Le solde de {amount} sera à régler par virement bancaire à réception de votre facture, avant le démarrage des cours.",
        "deposit_balance_due": "Le solde de {amount} sera à régler {due_label}.",
        "deposit_balance_schedule": "Le solde sera à régler selon l’échéancier indiqué ci-dessous.",
        "deposit_confirm": "Pour confirmer votre inscription et bloquer votre créneau, un acompte est requis dès validation du devis.",
        "deposit_amount_due": "Acompte à payer pour valider l’inscription",
        "deposit_none": "Aucun acompte préinscription.",
        "empty_lines": "Aucune ligne.",
        "identity_child_title": "Informations de l’élève",
        "identity_adult_title": "Informations de l’adulte responsable",
        "payment_instructions": "Consignes",
        "course_solfege": "Cours de solfège",
        "course_solfege_online": "Cours de solfège en ligne",
        "course_solfege_level": "niveau {level}",
        "course_included_quote": "inclus dans le devis",
        "to_select": "à sélectionner",
        "to_select_short": "à choisir",
        "solfege_option_included": "Option solfège : incluse dans le présent devis.",
        "solfege_estimated_level": "Niveau estimé",
        "solfege_slot_selected": "Créneau retenu",
        "solfege_slots_available": "Créneaux disponibles",
        "solfege_subscribed_summary": "Solfège souscrit - Niveau {level}{duration}{slot}",
        "solfege_pending_notice": "Le tarif total du présent devis inclut le solfège en ligne. Seul le choix du créneau reste à confirmer.",
        "masterclass_subscribed": "Masterclass du samedi souscrite.",
        "masterclass_subscribed_with_slots": "Masterclass du samedi souscrite - {slots}",
        "masterclass_option_subscribed": "Option Masterclass du samedi : souscrite.",
        "masterclass_common_text": "Masterclass du samedi (complément aux 2 cours collectifs hebdomadaires) : une session de 3h dédiée à la pratique au piano, avec un focus approfondi sur la musicalité et l’interprétation.",
        "end_year_concert_option_subscribed": "Option Concert de fin d’année : souscrite.",
        "end_year_concert_option_not_subscribed": "Option Concert de fin d’année : non souscrite.",
        "end_year_concert_common_text": "Participation au concert de fin d’année de Piano Académie.",
        "pass_recup_option_subscribed": "Option Pass Récup : souscrite.",
        "pass_recup_option_not_subscribed": "Option Pass Récup : non souscrite.",
        "pass_recup_common_text": "Le Pass Récup’ permet de rattraper un cours collectif manqué, dans la limite de 4 rattrapages par année scolaire. Le rattrapage peut s’effectuer soit sur un cours collectif en présentiel, sous réserve de disponibilité d’un créneau, soit sur un cours collectif en ligne, sur des créneaux dédiés. Le pass est utilisable uniquement en cas d’absence signalée. Il est valable pour l’année scolaire en cours et n’est pas remboursable. Sans souscription à ce pass, aucun rattrapage ne pourra être proposé, quelle que soit la raison de l’absence.",
        "pass_recup_compact_text": "Ce pass permet de rattraper un cours collectif manqué sur un créneau en présentiel (si une place est disponible), ou à défaut, sur un créneau collectif en ligne dédié.",
        "pass_recup_compact_limit": "Limité à 4 rattrapages par an",
    },
    "en": {
        "schedule_due_invoice": "upon receipt of your invoice",
        "schedule_due_validation": "when the quote is approved, before your first lesson",
        "schedule_due_before_first_course": "before the first lesson starts",
        "payment_method_bank": "bank transfer",
        "payment_method_check_one": "check",
        "payment_method_check_many": "checks",
        "payment_method_card": "card payment",
        "payment_method_generic": "payment",
        "check_instruction_order": "Checks must be made payable to {payee}.",
        "check_instruction_send": "Please sign your checks and send them to: Piano Academie, 1 rue de Richelieu, 75001 PARIS.",
        "check_instruction_split_send_all": "When paying in several installments by check, all checks must be sent before lessons begin.",
        "check_instruction_deposit_card": "The deposit of {deposit_amount} must be paid by card when the quote is approved. A deposit invoice will be sent to you with the payment link.",
        "deposit_bank_line_1": "To secure the slot, a deposit of {deposit_amount} must be paid by bank transfer as soon as the quote is approved.",
        "deposit_bank_line_2": "A deposit invoice will be issued after the quote is approved.",
        "deposit_bank_line_3": "The remaining balance of {remaining_amount} must be paid by bank transfer upon receipt of the balance invoice, before lessons begin.",
        "deposit_card_line_1": "A deposit of {deposit_amount} must be paid when the quote is approved in order to secure the slot.",
        "deposit_card_line_2": "A deposit invoice will be sent and must be paid shortly after online approval.",
        "deposit_card_line_3": "The remaining balance of {remaining_amount} must be paid by card upon receipt of the corresponding invoice, before lessons begin.",
        "payment_balance_bank_invoice": "payment of the remaining balance of {amount} by bank transfer upon receipt of your invoice, before lessons begin",
        "payment_sentence_generic": "{method_subject} of {amount} due {due_label}",
        "payment_deposit_then": "After the deposit of {deposit_amount} {currency} is paid by card, {remaining_sentence}.",
        "payment_installments_after_deposit": "After the deposit of {deposit_amount} {currency} is paid by card, the balance is due in {count} installments as detailed below.",
        "payment_deposit_invoice_without_schedule": "A deposit invoice for {deposit_amount} will first be sent to secure your slot.",
        "payment_installments": "Payment is scheduled in {count} installments as detailed below.",
        "payment_deposit_only": "The deposit of {deposit_amount} {currency} must be paid by card when the quote is approved in order to secure the slot.",
        "payment_not_scheduled": "Payment schedule not specified",
        "quote_status_approved": "Approved on",
        "quote_status_validity": "Validity",
        "quote_status_valid_until": "Valid until {date}",
        "calendar_month_1": "January",
        "calendar_month_2": "February",
        "calendar_month_3": "March",
        "calendar_month_4": "April",
        "calendar_month_5": "May",
        "calendar_month_6": "June",
        "calendar_month_7": "July",
        "calendar_month_8": "August",
        "calendar_month_9": "September",
        "calendar_month_10": "October",
        "calendar_month_11": "November",
        "calendar_month_12": "December",
        "calendar_heading_default": "Course {index}",
        "calendar_no_sessions": "No lessons scheduled",
        "calendar_summary": "{session_count} {session_label} for {activity_count} {activity_label}",
        "calendar_session_singular": "scheduled lesson",
        "calendar_session_plural": "scheduled lessons",
        "calendar_activity_singular": "activity",
        "calendar_activity_plural": "activities",
        "weekday_0": "Monday",
        "weekday_1": "Tuesday",
        "weekday_2": "Wednesday",
        "weekday_3": "Thursday",
        "weekday_4": "Friday",
        "weekday_5": "Saturday",
        "weekday_6": "Sunday",
        "modality_default": "Course",
        "modality_online": "Online",
        "modality_onsite": "On-site",
        "modality_hybrid": "Hybrid",
        "slot_mode_online": "Mode: online lesson",
        "slot_mode_onsite": "Mode: on-site lesson",
        "slot_mode_hybrid": "Mode: on-site or online lesson",
        "planning_type_activity": "Activity type",
        "planning_activity": "Activity",
        "planning_location": "Location",
        "planning_day": "Day",
        "planning_time": "Time",
        "planning_duration": "Duration",
        "planning_empty": "No planning blocks.",
        "schedule_label": "Installment",
        "schedule_amount": "Amount",
        "schedule_when": "Bank deposit",
        "schedule_type": "Type",
        "schedule_empty": "No payment schedule.",
        "calendar_date": "Date",
        "calendar_start": "Start",
        "calendar_end": "End",
        "calendar_modality": "Format",
        "calendar_empty": "No lessons scheduled.",
        "section_courses_options": "Selected lessons and options",
        "section_services": "Lessons included in the quote",
        "section_adjustments": "Applied discounts",
        "section_products": "Teaching materials",
        "section_kits": "Fees and services included in the enrollment",
        "section_other_fees": "Other fees",
        "section_schedule": "Payment schedule",
        "section_calendar": "Provisional lesson calendar",
        "cover_title": "Your enrollment quote",
        "cover_quote": "Quote",
        "cover_school_year": "School year",
        "cover_student": "Student",
        "identity_title": "Student and guardian information",
        "identity_child": "Student",
        "identity_birth_date": "Date of birth",
        "identity_adult_contact": "Responsible adult",
        "identity_adult_contact_email": "Responsible adult email",
        "identity_adult_contact_phone": "Responsible adult phone",
        "identity_adult_contact_address": "Responsible adult address",
        "identity_email": "Email",
        "identity_phone": "Phone",
        "identity_address": "Address",
        "table_quantity": "Quantity",
        "table_vat": "VAT",
        "table_unit_price_ttc": "Unit price incl. tax",
        "table_total_ttc": "Amount incl. tax",
        "table_material": "Material",
        "table_kit": "Kit",
        "kit_includes": "Includes",
        "table_type": "Type",
        "table_title": "Title",
        "table_category": "Category",
        "empty_activity": "No activities.",
        "empty_material": "No materials.",
        "empty_kit": "No kits.",
        "empty_adjustment": "No discounts or surcharges.",
        "empty_other_fee": "No other fees.",
        "fee_discount": "Discount",
        "fee_surcharge": "Surcharge",
        "fee_service": "Service",
        "fee_material": "Material",
        "fee_kit": "Kit",
        "financial_title": "Total quote amount",
        "financial_total_before_adjustment": "Gross total before adjustment",
        "financial_adjustment": "Adjustment",
        "financial_impact": "Impact",
        "financial_adjustment_date": "Adjustment date",
        "financial_total_ht_invoice": "Net invoice total",
        "financial_vat_invoice": "Invoice VAT ({rate}%)",
        "financial_total_ttc_quote": "Gross quote total",
        "financial_total_ht": "Net total",
        "financial_vat": "VAT ({rate}%)",
        "payment_title": "Payment and schedule",
        "payment_method": "Payment method",
        "options_title": "Your options",
        "calendar_title": "Provisional lesson calendar",
        "calendar_overview": "Calendar overview: {summary}",
        "calendar_course_place": "Lesson / location",
        "calendar_course_count": "Number of lessons",
        "calendar_course_count_value": "{count} lessons",
        "semester_1": "Semester 1",
        "semester_2": "Semester 2",
        "calendar_course_dates": "Lesson dates",
        "calendar_no_session_short": "No lessons",
        "terms_title": "Enrollment terms 2026–2027",
        "terms_version_unspecified": "Version not specified",
        "payment_method_unspecified": "Payment method not specified",
        "compact_notice_one": "1 installment: {due_label}",
        "compact_notice_many": "Payment in {count} installments. The detailed schedule is communicated separately.",
        "table_semester": "Semester",
        "table_month": "Month",
        "terms_empty": "No general terms.",
        "terms_snapshot_empty": "No terms snapshot available.",
        "quote_recipient": "Recipient",
        "prospect_type": "Prospect type",
        "prospect_type_child": "Child",
        "prospect_type_adult": "Adult",
        "generated_at": "Document generated on",
        "financial_adjustment_credit": "Credit",
        "financial_adjustment_debt": "Debt",
        "financial_adjustment_none": "None",
        "financial_adjustment_credit_impact": "Deducted from the invoiced total",
        "financial_adjustment_debt_impact": "Added to the invoiced total",
        "financial_adjustment_none_html": "No credit or debt applied.",
        "financial_label": "Label",
        "financial_deposit": "Enrollment deposit",
        "financial_remaining_after_deposit": "Remaining balance after deposit",
        "financial_remaining_ht": "Remaining net total",
        "financial_remaining_vat": "Remaining VAT ({rate}%)",
        "deposit_section_title": "Enrollment deposit",
        "deposit_balance_bank_due": "The remaining balance of {amount} must be paid by bank transfer upon receipt of your invoice, before lessons begin.",
        "deposit_balance_due": "The remaining balance of {amount} must be paid {due_label}.",
        "deposit_balance_schedule": "The remaining balance will be paid according to the schedule below.",
        "deposit_confirm": "To confirm your enrollment and secure your slot, a deposit is required as soon as the quote is approved.",
        "deposit_amount_due": "Deposit due to confirm enrollment",
        "deposit_none": "No enrollment deposit.",
        "empty_lines": "No lines.",
        "identity_child_title": "Student information",
        "identity_adult_title": "Responsible adult information",
        "payment_instructions": "Instructions",
        "course_solfege": "Music theory lesson",
        "course_solfege_online": "Online music theory lesson",
        "course_solfege_level": "level {level}",
        "course_included_quote": "included in the quote",
        "to_select": "to be selected",
        "to_select_short": "to choose",
        "solfege_option_included": "Music theory option: included in this quote.",
        "solfege_estimated_level": "Estimated level",
        "solfege_slot_selected": "Selected slot",
        "solfege_slots_available": "Available slots",
        "solfege_subscribed_summary": "Music theory included - Level {level}{duration}{slot}",
        "solfege_pending_notice": "The total amount of this quote includes online music theory. Only the slot selection still needs to be confirmed.",
        "masterclass_subscribed": "Saturday masterclass selected.",
        "masterclass_subscribed_with_slots": "Saturday masterclass selected - {slots}",
        "masterclass_option_subscribed": "Saturday Masterclass option: selected.",
        "masterclass_common_text": "Saturday masterclass (in addition to the two weekly group lessons): a 3-hour session dedicated to piano practice, with a deeper focus on musicality and interpretation.",
        "end_year_concert_option_subscribed": "End-of-year concert option: selected.",
        "end_year_concert_option_not_subscribed": "End-of-year concert option: not selected.",
        "end_year_concert_common_text": "Participation in Piano Academie's end-of-year concert.",
        "pass_recup_option_subscribed": "Catch-up Pass option: selected.",
        "pass_recup_option_not_subscribed": "Catch-up Pass option: not selected.",
        "pass_recup_common_text": "The Catch-up Pass lets you make up for a missed group lesson, up to 4 catch-ups per school year. Catch-up may take place either in an on-site group lesson, subject to slot availability, or in a dedicated online group lesson. The pass can only be used when an absence has been reported. It is valid for the current school year and is non-refundable. Without this pass, no catch-up can be offered, whatever the reason for the absence.",
        "pass_recup_compact_text": "This pass lets you make up a missed group lesson in an on-site slot (if a place is available), or otherwise in a dedicated online group slot.",
        "pass_recup_compact_limit": "Limited to 4 catch-ups per year",
    },
}


def _quote_doc_language(quote: Quote | None = None, language: str | None = None) -> str:
    if language is not None:
        return normalize_language(language)
    if quote is not None:
        return normalize_language(getattr(quote, "language", None))
    return normalize_language(None)


def _quote_doc_text(key: str, *, quote: Quote | None = None, language: str | None = None, **values: object) -> str:
    normalized_language = _quote_doc_language(quote=quote, language=language)
    template = QUOTE_DOC_TEXT.get(normalized_language, QUOTE_DOC_TEXT["fr"]).get(key, key)
    return template.format(**values)


def _quote_doc_month_label(month: int, *, language: str | None = None) -> str:
    return _quote_doc_text(f"calendar_month_{month}", language=language)


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "oui"}


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _format_address_parts(
    *,
    address_line: str = "",
    address_line_2: str = "",
    postal_code: str = "",
    city: str = "",
    country: str = "",
) -> str:
    locality = " ".join(part for part in [postal_code.strip(), city.strip()] if part).strip()
    parts = [part.strip() for part in [address_line, address_line_2, locality, country] if part and part.strip()]
    return ", ".join(parts)


def _typeform_parent_address_parts_from_normalized_payload(normalized: dict[str, Any]) -> dict[str, str]:
    normalized = _json_object(normalized)
    return {
        "address_line": str(
            normalized.get("parent_address_line_1")
            or normalized.get("adult_address_line_1")
            or normalized.get("parent_address")
            or normalized.get("adult_address")
            or normalized.get("address")
            or ""
        ).strip(),
        "address_line_2": str(normalized.get("parent_address_line_2") or normalized.get("adult_address_line_2") or "").strip(),
        "postal_code": str(normalized.get("parent_postal_code") or normalized.get("adult_postal_code") or "").strip(),
        "city": str(normalized.get("parent_city") or normalized.get("adult_city") or "").strip(),
        "country": str(normalized.get("parent_country") or normalized.get("adult_country") or "").strip(),
    }


def _typeform_parent_address_from_normalized_payload(normalized: dict[str, Any]) -> str:
    parts = _typeform_parent_address_parts_from_normalized_payload(normalized)
    return _format_address_parts(
        address_line=parts["address_line"],
        address_line_2=parts["address_line_2"],
        postal_code=parts["postal_code"],
        city=parts["city"],
        country=parts["country"],
    )


def _typeform_simplified_answer_value(simplified_answers: list[Any], *labels: str) -> str:
    expected = {str(label or "").strip().lower() for label in labels if str(label or "").strip()}
    if not expected:
        return ""
    for item in simplified_answers:
        row = _json_object(item)
        label = str(row.get("label") or row.get("field_label") or row.get("question") or "").strip().lower()
        if label not in expected:
            continue
        value = str(row.get("value") or "").strip()
        if value:
            return value
    return ""


def _typeform_contact_phone_from_normalized_payload(normalized: dict[str, Any]) -> str:
    normalized = _json_object(normalized)
    return str(
        normalized.get("parent_phone")
        or normalized.get("adult_phone")
        or normalized.get("phone")
        or normalized.get("telephone")
        or ""
    ).strip()


def _typeform_contact_phone_from_intake(intake: TypeformIntake | None) -> str:
    if intake is None:
        return ""
    phone = _typeform_contact_phone_from_normalized_payload(_json_object(intake.normalized_payload_json))
    if phone:
        return phone
    return _typeform_simplified_answer_value(
        _json_list(intake.simplified_response_json),
        "Phone number",
        "Telephone",
        "Téléphone",
        "Phone",
        "telephone",
    )


def _typeform_parent_address_from_intake(intake: TypeformIntake | None) -> str:
    parts = _typeform_parent_address_parts_from_intake(intake)
    return _format_address_parts(
        address_line=parts["address_line"],
        address_line_2=parts["address_line_2"],
        postal_code=parts["postal_code"],
        city=parts["city"],
        country=parts["country"],
    )


def _typeform_parent_address_parts_from_intake(intake: TypeformIntake | None) -> dict[str, str]:
    if intake is None:
        return {"address_line": "", "address_line_2": "", "postal_code": "", "city": "", "country": ""}
    parts = _typeform_parent_address_parts_from_normalized_payload(_json_object(intake.normalized_payload_json))
    simplified_answers = _json_list(intake.simplified_response_json)
    if not parts["address_line"]:
        parts["address_line"] = _typeform_simplified_answer_value(simplified_answers, "Address", "address", "Adresse", "adresse")
    if not parts["address_line_2"]:
        parts["address_line_2"] = _typeform_simplified_answer_value(
            simplified_answers,
            "Address line 2",
            "address line 2",
            "Adresse ligne 2",
            "Complement d'adresse",
            "Complément d'adresse",
        )
    if not parts["city"]:
        parts["city"] = _typeform_simplified_answer_value(simplified_answers, "City/Town", "city/town", "Ville", "ville")
    if not parts["postal_code"]:
        parts["postal_code"] = _typeform_simplified_answer_value(
            simplified_answers,
            "Zip/Post Code",
            "zip/post code",
            "Code postal",
            "code postal",
        )
    if not parts["country"]:
        parts["country"] = _typeform_simplified_answer_value(simplified_answers, "Country", "country", "Pays", "pays")
    return {key: str(value or "").strip() for key, value in parts.items()}


def _typeform_parent_address_from_quote(*, db: Session | None, quote: Quote) -> str:
    parts = _typeform_parent_address_parts_from_quote(db=db, quote=quote)
    return _format_address_parts(
        address_line=parts["address_line"],
        address_line_2=parts["address_line_2"],
        postal_code=parts["postal_code"],
        city=parts["city"],
        country=parts["country"],
    )


def _typeform_parent_address_parts_from_quote(*, db: Session | None, quote: Quote) -> dict[str, str]:
    quote_meta = _json_object(quote.meta)
    typeform_meta = _json_object(quote_meta.get("typeform_intake"))
    parts = _typeform_parent_address_parts_from_normalized_payload(_json_object(typeform_meta.get("normalized_payload")))
    if any(parts.values()):
        return parts
    intake_id = str(typeform_meta.get("intake_id") or "").strip()
    if not intake_id and db is not None and quote.prospect_id is not None:
        prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id))
        if prospect is not None:
            prospect_meta = _json_object(prospect.meta)
            intake_id = str(prospect_meta.get("typeform_intake_id") or "").strip()
    if db is None or not intake_id:
        return {"address_line": "", "address_line_2": "", "postal_code": "", "city": "", "country": ""}
    try:
        intake_uuid = UUID(intake_id)
    except ValueError:
        return {"address_line": "", "address_line_2": "", "postal_code": "", "city": "", "country": ""}
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_uuid))
    return _typeform_parent_address_parts_from_intake(intake)


def _typeform_contact_phone_from_quote(*, db: Session | None, quote: Quote) -> str:
    quote_meta = _json_object(quote.meta)
    typeform_meta = _json_object(quote_meta.get("typeform_intake"))
    phone = _typeform_contact_phone_from_normalized_payload(_json_object(typeform_meta.get("normalized_payload")))
    if phone:
        return phone
    intake_id = str(typeform_meta.get("intake_id") or "").strip()
    if not intake_id and db is not None and quote.prospect_id is not None:
        prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id))
        if prospect is not None:
            prospect_meta = _json_object(prospect.meta)
            intake_id = str(prospect_meta.get("typeform_intake_id") or "").strip()
    if db is None or not intake_id:
        return ""
    try:
        intake_uuid = UUID(intake_id)
    except ValueError:
        return ""
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_uuid))
    return _typeform_contact_phone_from_intake(intake)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decimal_str(value: Decimal) -> str:
    amount = Decimal(value or Decimal("0")).quantize(Decimal("0.01"))
    return f"{amount:.2f}".replace(".", ",")


def _decimal_from_any(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception:
        return default
    if not parsed.is_finite():
        return default
    return parsed


def _split_ttc_with_rate(total_ttc: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal]:
    ttc_amount = Decimal(total_ttc or Decimal("0")).quantize(Decimal("0.01"))
    rate = Decimal(vat_rate or Decimal("0")).quantize(Decimal("0.01"))
    if rate <= Decimal("0.00"):
        return ttc_amount, Decimal("0.00")
    divisor = Decimal("1.00") + (rate / Decimal("100"))
    if divisor <= Decimal("0.00"):
        return ttc_amount, Decimal("0.00")
    ht_amount = (ttc_amount / divisor).quantize(Decimal("0.01"))
    vat_amount = (ttc_amount - ht_amount).quantize(Decimal("0.01"))
    return ht_amount, vat_amount


def _resolve_display_vat_rate(
    *,
    quote: Quote,
    lines: list[QuoteLine],
    total_ht: Decimal,
    total_vat: Decimal,
) -> Decimal:
    non_zero_line_rates = {
        Decimal(getattr(line, "vat_rate", 0) or 0).quantize(Decimal("0.01"))
        for line in lines
        if Decimal(getattr(line, "amount_ttc", 0) or 0) != Decimal("0.00")
    }
    if len(non_zero_line_rates) == 1:
        return next(iter(non_zero_line_rates))

    explicit_quote_rate = _decimal_from_any(quote.vat_rate, default=Decimal("-1"))
    if explicit_quote_rate >= Decimal("0.00"):
        return explicit_quote_rate.quantize(Decimal("0.01"))

    quote_meta = _json_object(quote.meta)
    explicit_meta_rate = _decimal_from_any(quote_meta.get("tva_rate"), default=Decimal("-1"))
    if explicit_meta_rate >= Decimal("0.00"):
        return explicit_meta_rate.quantize(Decimal("0.01"))

    if total_ht <= Decimal("0.00"):
        return Decimal("0.00")
    return ((total_vat / total_ht) * Decimal("100")).quantize(Decimal("0.01"))


def _money(value: Decimal, currency: str) -> str:
    return f"{_decimal_str(value)} {currency}"


def _compact_quantity_label(value: Any) -> str:
    quantity = _decimal_from_any(value, Decimal("0"))
    if quantity == quantity.to_integral_value():
        return str(int(quantity))
    return _decimal_str(quantity)


def _schedule_due_label(item: dict[str, Any], *, language: str | None = None) -> str:
    due_type = str(item.get("due_type") or "").strip().lower()
    due_label = str(item.get("due_label") or "").strip()
    normalized = due_label.lower()
    if due_type == "on_registration":
        return _quote_doc_text("schedule_due_invoice", language=language)
    if due_type == "on_quote_validation_before_first_course":
        return _quote_doc_text("schedule_due_validation", language=language)
    if due_type == "before_first_course":
        return _quote_doc_text("schedule_due_before_first_course", language=language)
    if normalized in {
        "a reception",
        "a reception du dossier",
        "a reception de votre facture",
        "à reception",
        "à reception du dossier",
        "à reception de votre facture",
        "à réception",
        "à réception du dossier",
        "à réception de votre facture",
    }:
        return _quote_doc_text("schedule_due_invoice", language=language)
    if normalized in {
        "a la validation du devis, avant votre 1er cours",
        "à la validation du devis, avant votre 1er cours",
    }:
        return _quote_doc_text("schedule_due_validation", language=language)
    if due_label:
        return due_label
    return due_type or "-"


def _payment_schedule_method_subject(method_label: str, *, count: int, language: str | None = None) -> str:
    normalized = str(method_label or "").strip().lower()
    if "virement" in normalized:
        return _quote_doc_text("payment_method_bank", language=language)
    if "cheque" in normalized or "chèque" in normalized:
        return _quote_doc_text("payment_method_check_one" if count == 1 else "payment_method_check_many", language=language)
    if "carte" in normalized:
        return _quote_doc_text("payment_method_card", language=language)
    return _quote_doc_text("payment_method_generic", language=language)


def _is_bank_transfer_payment_method(method_label: str) -> bool:
    return "virement" in str(method_label or "").strip().lower()


def _is_card_payment_method(method_label: str) -> bool:
    return "carte" in str(method_label or "").strip().lower()


def _is_check_payment_method(method_label: str) -> bool:
    normalized = _searchable_text(method_label)
    return bool(re.search(r"\b(?:cheques?|checks?)\b", normalized))


def _normalise_check_schedule_deposit_months(
    schedule: list[dict[str, Any]],
    *,
    language: str | None = None,
) -> list[dict[str, Any]]:
    normalised = [dict(item) for item in schedule]
    if len(normalised) <= 1:
        return normalised
    has_check_installments = any(
        _is_check_payment_method(str(item.get("payment_method") or item.get("label") or ""))
        for item in normalised
    )
    if not has_check_installments:
        return normalised
    first = normalised[0]
    first["due_type"] = "before_first_course"
    first["due_label"] = _quote_doc_text("schedule_due_before_first_course", language=language)

    second = normalised[1]
    second_label = _searchable_text(second.get("label"))
    if "cheque" not in second_label and "check" not in second_label:
        return normalised
    if second.get("due_month") or str(second.get("due_label") or "").strip():
        return normalised
    second["due_month"] = 12
    second["due_label"] = _quote_doc_text("calendar_month_12", language=language).lower()
    return normalised


def _quote_legal_entity_name(*, db: Session | None, quote: Quote) -> str:
    if db is not None and getattr(quote, "legal_entity_id", None) is not None:
        entity = db.scalar(select(LegalEntity).where(LegalEntity.id == quote.legal_entity_id))
        if entity is not None:
            name = str(entity.name or "").strip()
            if name:
                return name
    meta = _json_object(getattr(quote, "meta", None))
    for key in ("legal_entity_name", "seller_legal_entity_name", "billing_entity_name", "billing_entity"):
        name = str(meta.get(key) or "").strip()
        if name:
            return name
    return ""


def _check_payee_for_legal_entity(legal_entity_name: str) -> str:
    normalized = _searchable_text(legal_entity_name)
    if "services" in normalized:
        return "PIANO ACADEMIE SERVICES"
    return "PIANO ACADEMIE"


def _check_payment_instruction_lines(
    *,
    payment_method_label: str,
    schedule: list[dict[str, Any]],
    legal_entity_name: str,
    has_deposit: bool,
    deposit_amount_ttc: Decimal = Decimal("0.00"),
    currency: str = "EUR",
    language: str | None = None,
) -> list[str]:
    method_labels = [payment_method_label, *(str(item.get("payment_method") or "") for item in schedule)]
    if not any(_is_check_payment_method(label) for label in method_labels):
        return []
    check_installment_count = sum(
        1
        for item in schedule
        if _is_check_payment_method(str(item.get("payment_method") or payment_method_label or ""))
    )
    payee = _check_payee_for_legal_entity(legal_entity_name)
    lines = [
        _quote_doc_text("check_instruction_order", language=language, payee=payee),
        _quote_doc_text("check_instruction_send", language=language),
    ]
    if check_installment_count > 1:
        lines.append(_quote_doc_text("check_instruction_split_send_all", language=language))
    if has_deposit:
        lines.insert(
            0,
            _quote_doc_text(
                "check_instruction_deposit_card",
                language=language,
                deposit_amount=_money(deposit_amount_ttc, currency),
            ),
        )
    return lines


def _bank_transfer_deposit_schedule_lines(
    *,
    schedule: list[dict[str, Any]],
    has_deposit: bool,
    deposit_amount_ttc: Decimal,
    currency: str,
    payment_method_label: str,
    remaining_ttc_after_deposit: Decimal,
    language: str | None = None,
) -> list[str]:
    if not has_deposit or deposit_amount_ttc <= Decimal("0.00") or remaining_ttc_after_deposit <= Decimal("0.00"):
        return []
    if len(schedule) != 1:
        return []
    item = schedule[0]
    item_method_label = str(item.get("payment_method") or payment_method_label or "").strip()
    if not _is_bank_transfer_payment_method(item_method_label):
        return []
    if _schedule_due_label(item, language=language) != _quote_doc_text("schedule_due_invoice", language=language):
        return []
    deposit_amount = _money(deposit_amount_ttc, currency)
    remaining_amount = _money(remaining_ttc_after_deposit, currency)
    return [
        _quote_doc_text("deposit_bank_line_1", language=language, deposit_amount=deposit_amount),
        _quote_doc_text("deposit_bank_line_2", language=language),
        _quote_doc_text("deposit_bank_line_3", language=language, remaining_amount=remaining_amount),
    ]


def _card_deposit_schedule_lines(
    *,
    schedule: list[dict[str, Any]],
    has_deposit: bool,
    deposit_amount_ttc: Decimal,
    currency: str,
    payment_method_label: str,
    remaining_ttc_after_deposit: Decimal,
    language: str | None = None,
) -> list[str]:
    if not has_deposit or deposit_amount_ttc <= Decimal("0.00") or remaining_ttc_after_deposit <= Decimal("0.00"):
        return []
    if len(schedule) != 1:
        return []
    item = schedule[0]
    item_method_label = str(item.get("payment_method") or payment_method_label or "").strip()
    if not _is_card_payment_method(item_method_label):
        return []
    if _schedule_due_label(item, language=language) != _quote_doc_text("schedule_due_invoice", language=language):
        return []
    deposit_amount = _money(deposit_amount_ttc, currency)
    remaining_amount = _money(remaining_ttc_after_deposit, currency)
    return [
        _quote_doc_text("deposit_card_line_1", language=language, deposit_amount=deposit_amount),
        _quote_doc_text("deposit_card_line_2", language=language),
        _quote_doc_text("deposit_card_line_3", language=language, remaining_amount=remaining_amount),
    ]


def _payment_schedule_summary_text(
    *,
    schedule: list[dict[str, Any]],
    has_deposit: bool,
    deposit_amount_ttc: Decimal,
    currency: str,
    payment_method_label: str,
    remaining_ttc_after_deposit: Decimal,
    language: str | None = None,
) -> str:
    if special_lines := _bank_transfer_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        payment_method_label=payment_method_label,
        remaining_ttc_after_deposit=remaining_ttc_after_deposit,
        language=language,
    ):
        return " ".join(special_lines)
    if special_lines := _card_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        payment_method_label=payment_method_label,
        remaining_ttc_after_deposit=remaining_ttc_after_deposit,
        language=language,
    ):
        return " ".join(special_lines)

    if schedule:
        if len(schedule) == 1:
            item = schedule[0]
            amount = _money(
                _decimal_from_any(item.get("amount_ttc"), Decimal("0.00")),
                str(item.get("currency") or currency or "EUR"),
            )
            item_method_label = str(item.get("payment_method") or payment_method_label or "").strip()
            method_subject = _payment_schedule_method_subject(item_method_label, count=1, language=language)
            due_label = _schedule_due_label(item, language=language)
            if _is_bank_transfer_payment_method(item_method_label) and due_label == _quote_doc_text("schedule_due_invoice", language=language):
                remaining_sentence = _quote_doc_text("payment_balance_bank_invoice", language=language, amount=amount)
            else:
                remaining_sentence = _quote_doc_text(
                    "payment_sentence_generic",
                    language=language,
                    method_subject=method_subject,
                    amount=amount,
                    due_label=due_label,
                )
            if has_deposit:
                return _quote_doc_text(
                    "payment_deposit_then",
                    language=language,
                    deposit_amount=_decimal_str(deposit_amount_ttc),
                    currency=currency,
                    remaining_sentence=remaining_sentence,
                )
            return f"{remaining_sentence}."

        if has_deposit:
            return _quote_doc_text(
                "payment_installments_after_deposit",
                language=language,
                deposit_amount=_decimal_str(deposit_amount_ttc),
                currency=currency,
                count=len(schedule),
            )
        return _quote_doc_text("payment_installments", language=language, count=len(schedule))

    if has_deposit and remaining_ttc_after_deposit <= Decimal("0.00"):
        return _quote_doc_text(
            "payment_deposit_only",
            language=language,
            deposit_amount=_decimal_str(deposit_amount_ttc),
            currency=currency,
        )
    return _quote_doc_text("payment_not_scheduled", language=language)


def _name(first_name: str | None, last_name: str | None, fallback: str = "-") -> str:
    value = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
    return value or fallback


def _date_label(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(timezone.utc).strftime("%d/%m/%Y")


def display_quote_expires_at(quote: Quote, *, reference_at: datetime | None = None) -> datetime | None:
    if quote.expires_at is not None:
        return quote.expires_at
    expiry_days = int(getattr(quote, "expiry_days", None) or 10)
    if quote.sent_at is not None:
        return quote.sent_at + timedelta(days=expiry_days)
    normalized_status = str(getattr(quote, "status", "") or "").strip().lower()
    if normalized_status in {"created", "change_requested"}:
        base = reference_at or _utcnow()
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        return base.astimezone(timezone.utc) + timedelta(days=expiry_days)
    return None


def _datetime_label(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M")


def _paris_datetime_label(value: datetime | None) -> str:
    if value is None:
        return "-"
    try:
        paris_zone = ZoneInfo("Europe/Paris")
    except Exception:
        paris_zone = timezone.utc
    return value.astimezone(paris_zone).strftime("%d/%m/%Y %H:%M")


def _quote_status_date_display(quote: Quote) -> tuple[str, str, str]:
    language = _quote_doc_language(quote=quote)
    normalized_status = str(quote.status or "").strip().lower()
    if normalized_status == "approved" and quote.approved_at is not None:
        approval_value = _paris_datetime_label(quote.approved_at)
        return (
            _quote_doc_text("quote_status_approved", language=language),
            approval_value,
            f"{_quote_doc_text('quote_status_approved', language=language)} {approval_value}",
        )
    expiry_value = _date_label(display_quote_expires_at(quote))
    return (
        _quote_doc_text("quote_status_validity", language=language),
        expiry_value,
        _quote_doc_text("quote_status_valid_until", language=language, date=expiry_value),
    )


def _replace_expiration_mentions_for_approved_quote(content: str, quote: Quote) -> str:
    normalized_status = str(quote.status or "").strip().lower()
    if normalized_status != "approved" or quote.approved_at is None:
        return content
    rendered = str(content or "")
    if not rendered:
        return rendered
    expiry_value = _date_label(display_quote_expires_at(quote))
    approval_value = _paris_datetime_label(quote.approved_at)
    replacements = {
        f"Validité : <strong>{expiry_value}</strong>": f"Approuvé le : <strong>{approval_value}</strong>",
        f"Validite : <strong>{expiry_value}</strong>": f"Approuvé le : <strong>{approval_value}</strong>",
        f"Validité : {expiry_value}": f"Approuvé le : {approval_value}",
        f"Validite : {expiry_value}": f"Approuvé le : {approval_value}",
        f"Expiration : <strong>{expiry_value}</strong>": f"Approuvé le : <strong>{approval_value}</strong>",
        f"Expiration: <strong>{expiry_value}</strong>": f"Approuvé le : <strong>{approval_value}</strong>",
        f"Expiration : {expiry_value}": f"Approuvé le : {approval_value}",
        f"Expiration: {expiry_value}": f"Approuvé le : {approval_value}",
        f"Valable jusqu’au {expiry_value}": f"Approuvé le {approval_value}",
        f"Valable jusqu au {expiry_value}": f"Approuvé le {approval_value}",
    }
    for source, target in replacements.items():
        rendered = rendered.replace(source, target)
    return rendered


def _birth_date_label(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, date_format).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw


def _document_style_html() -> str:
    return (
        "<style>"
        "body{font-family:Arial,Helvetica,sans-serif;color:#1f1f1f;font-size:11px;line-height:1.4;}"
        "h1,h2,h3{color:#111827;margin:0 0 8px 0;page-break-after:avoid;}"
        "p{margin:0 0 8px 0;}"
        ".quote-muted{color:#5b6470;}"
        ".quote-page-break{page-break-before:always;}"
        ".quote-block{border:1px solid #d4dae3;background:#fbfcfe;padding:10px;margin:0 0 10px 0;page-break-inside:auto;}"
        ".quote-identity-grid{display:block;width:100%;}"
        ".quote-identity-card{border:1px solid #d3dbe7;background:#ffffff;padding:10px 12px;margin:0 0 10px 0;page-break-inside:avoid;}"
        ".quote-identity-card h3{margin:0 0 8px 0;font-size:13px;color:#111827;}"
        ".quote-identity-meta{width:100%;border-collapse:collapse;font-size:11px;}"
        ".quote-identity-meta td{padding:6px 8px;border-bottom:1px solid #edf2f7;vertical-align:top;}"
        ".quote-identity-meta tr:last-child td{border-bottom:none;}"
        ".quote-identity-meta td:first-child{width:36%;font-weight:700;color:#1f2937;background:#f8fafc;}"
        ".quote-header{width:100%;border-collapse:collapse;margin:0 0 10px 0;}"
        ".quote-header td{vertical-align:top;}"
        ".quote-brand-logo{display:inline-block;min-width:84px;padding:7px 9px;background:#111111;color:#d2b04c;font-size:10px;line-height:1.2;font-weight:700;letter-spacing:0.5px;text-align:center;}"
        ".quote-brand-logo-img{display:inline-block;max-width:140px;max-height:70px;object-fit:contain;}"
        ".quote-cover{text-align:center;min-height:220mm;padding-top:30mm;}"
        ".quote-cover-title{font-size:28px;letter-spacing:0.3px;text-transform:uppercase;margin-bottom:6mm;}"
        ".quote-cover-subtitle{font-size:14px;color:#4b5563;margin-bottom:9mm;}"
        ".quote-cover-name{font-size:22px;margin-bottom:4mm;}"
        ".quote-cover-meta{font-size:12px;color:#4b5563;line-height:1.6;}"
        ".quote-small-muted{font-size:10px;line-height:1.45;color:#6b7280;}"
        ".quote-table{width:100%;border-collapse:collapse;border-spacing:0;margin:6px 0 10px 0;font-size:11px;table-layout:auto;}"
        ".quote-table thead{display:table-header-group;}"
        ".quote-table tfoot{display:table-footer-group;}"
        ".quote-table tr{page-break-inside:avoid;}"
        ".quote-table th{background:#e7edf7 !important;color:#111827 !important;border:1px solid #c2ccda !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;text-align:left !important;font-weight:700 !important;line-height:1.4 !important;vertical-align:middle !important;height:auto !important;min-height:30px;white-space:normal !important;word-break:break-word !important;overflow-wrap:anywhere !important;}"
        ".quote-table td{border:1px solid #d3dbe7 !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;vertical-align:middle !important;color:#111827 !important;line-height:1.45 !important;height:auto !important;min-height:30px;white-space:normal !important;word-break:break-word !important;overflow-wrap:anywhere !important;}"
        ".quote-table td>*{margin-top:0;margin-bottom:0;}"
        ".quote-footer{width:100%;border-collapse:collapse;margin-top:12px;padding-top:8px;border-top:1px solid #cdd4de;font-size:10px;color:#475467;}"
        ".quote-footer td{vertical-align:top;}"
        ".quote-terms-title{margin-top:0;}"
        "</style>"
    )


def _account_logo_data_url(*, db: Session | None) -> str:
    if db is None:
        return ""
    row = db.scalar(select(AppSetting).where(AppSetting.key == ACCOUNT_LOGO_SETTING_KEY))
    if row is None:
        return ""
    value = str(row.value or "").strip()
    if not value.lower().startswith("data:image/"):
        return ""
    return value


def _brand_logo_html(*, db: Session | None, variant: str = "header") -> str:
    logo_data_url = _account_logo_data_url(db=db)
    if logo_data_url:
        width_px = "118" if variant == "cover" else "86"
        return (
            "<img "
            "class='quote-brand-logo-img' "
            f"src='{escape(logo_data_url)}' "
            f"width='{width_px}' "
            "style='display:block;width:auto;height:auto;' "
            "alt='Piano Academie'/>"
        )
    return "<div class='quote-brand-logo'>PIANO<br/>ACADEMIE</div>"


def _session_date_parts(value: object) -> tuple[int, int, int] | None:
    raw = str(value or "").strip()
    parsed = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if parsed is None:
        return None
    year = int(parsed.group(1))
    month = int(parsed.group(2))
    day = int(parsed.group(3))
    if year < 1900 or year > 3000 or month < 1 or month > 12 or day < 1 or day > 31:
        return None
    return year, month, day


def _session_month_day(value: object) -> tuple[int, int] | None:
    parsed = _session_date_parts(value)
    if parsed is None:
        return None
    _, month, day = parsed
    return month, day


def _calendar_semester_rows(
    month_map: dict[tuple[int, int], set[int]],
    *,
    semester: int,
    language: str | None = None,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for year, month in sorted(month_map.keys()):
        if semester == 1 and not (month >= 9 or month <= 1):
            continue
        if semester == 2 and not (2 <= month <= 8):
            continue
        days = sorted(month_map.get((year, month)) or set())
        if not days:
            continue
        rows.append((f"{_quote_doc_month_label(month, language=language)} {year}", ", ".join(str(day) for day in days)))
    return rows


def _calendar_group_heading(title: Any, index: int, *, language: str | None = None) -> str:
    cleaned = str(title or "").strip()
    if not cleaned or cleaned.lower() in {"activite", "activité", "cours"}:
        return _quote_doc_text("calendar_heading_default", language=language, index=index)
    if _is_english_quote_language(language) and "·" in cleaned:
        raw_activity, raw_location = [part.strip() for part in cleaned.split("·", 1)]
        activity = _localized_business_label(raw_activity, language=language)
        location = _localized_location_label(raw_location, language=language)
        return f"{activity} · {location}" if location else activity
    return cleaned


def _calendar_summary_text(*, session_count: int, activity_count: int, language: str | None = None) -> str:
    if session_count <= 0:
        return _quote_doc_text("calendar_no_sessions", language=language)
    session_label = _quote_doc_text(
        "calendar_session_singular" if session_count == 1 else "calendar_session_plural",
        language=language,
    )
    activity_label = _quote_doc_text(
        "calendar_activity_singular" if activity_count == 1 else "calendar_activity_plural",
        language=language,
    )
    return _quote_doc_text(
        "calendar_summary",
        language=language,
        session_count=session_count,
        session_label=session_label,
        activity_count=activity_count,
        activity_label=activity_label,
    )


def _calendar_visual_summary(sessions: list[dict[str, Any]], *, language: str | None = None) -> tuple[str, int]:
    grouped: dict[str, dict[tuple[int, int], set[int]]] = {}
    for session in sessions:
        parsed = _session_date_parts(session.get("date"))
        if parsed is None:
            continue
        year, month, day = parsed
        activity_label = str(session.get("activity_label") or "").strip() or _quote_doc_text("calendar_heading_default", language=language, index=1)
        location_label = str(session.get("location_label") or "").strip()
        title = f"{activity_label} · {location_label}" if location_label else activity_label
        if title not in grouped:
            grouped[title] = {}
        if (year, month) not in grouped[title]:
            grouped[title][(year, month)] = set()
        grouped[title][(year, month)].add(day)

    if not grouped:
        return f"<p>{escape(_quote_doc_text('calendar_no_sessions', language=language))}</p>", 0

    blocks: list[str] = []
    for index, title in enumerate(sorted(grouped.keys()), start=1):
        heading = _calendar_group_heading(title, index, language=language)
        month_map = grouped[title]
        count = sum(len(values) for values in month_map.values())
        sem1 = _calendar_semester_rows(month_map, semester=1, language=language)
        sem2 = _calendar_semester_rows(month_map, semester=2, language=language)

        semester_rows: list[tuple[str, str, str]] = []
        for month_label, days in sem1:
            semester_rows.append((_quote_doc_text("semester_1", language=language), month_label, days))
        for month_label, days in sem2:
            semester_rows.append((_quote_doc_text("semester_2", language=language), month_label, days))
        if not semester_rows:
            semester_rows.append(("-", "-", _quote_doc_text("calendar_no_session_short", language=language)))
        course_count_value = _quote_doc_text("calendar_course_count_value", language=language, count=count)
        semesters_html = "".join(
            "<tr>"
            f"<td valign='middle' style='border:1px solid #d8dee7;padding:10px;vertical-align:middle;'>{escape(semester)}</td>"
            f"<td valign='middle' style='border:1px solid #d8dee7;padding:10px;vertical-align:middle;'><strong>{escape(month_label)}</strong></td>"
            f"<td valign='top' style='border:1px solid #d8dee7;padding:10px;vertical-align:top;'>{escape(days)}</td>"
            "</tr>"
            for semester, month_label, days in semester_rows
        )

        separator_html = (
            "<div style='height:8px;margin:6px 0 10px 0;border-top:2px dashed #d8deea;'></div>"
            if index > 1
            else ""
        )
        blocks.append(
            separator_html
            + "<div style='border:2px solid #cfd6e2;padding:0;margin:0 0 22px 0;page-break-inside:auto;background:#ffffff;'>"
            "<div style='background:#f8fafc;border-bottom:1px solid #d6d9de;padding:8px 10px;font-weight:700;color:#0f172a;'>"
            f"{escape(heading)}"
            "</div>"
            "<div style='padding:8px;'>"
            "<table class='quote-table' border='1' cellspacing='0' cellpadding='10' width='100%' "
            "style='width:100%;border-collapse:collapse;border-spacing:0;margin:0 0 8px 0;font-size:11px;'>"
            "<tbody>"
            "<tr>"
            "<td bgcolor='#DDE8FA' "
            f"style='background-color:#DDE8FA;color:#111827;border:1px solid #c2ccda;padding:12px 10px;text-align:left;font-weight:700;'>{escape(_quote_doc_text('calendar_course_place', language=language))}</td>"
            "<td bgcolor='#DDE8FA' align='right' "
            f"style='background-color:#DDE8FA;color:#111827;border:1px solid #c2ccda;padding:12px 10px;text-align:right;font-weight:700;'>{escape(_quote_doc_text('calendar_course_count', language=language))}</td>"
            "</tr>"
            f"<tr><td valign='middle' style='border:1px solid #d8dee7;padding:12px 10px;vertical-align:middle;'><strong>{escape(heading)}</strong></td><td align='right' valign='middle' style='border:1px solid #d8dee7;padding:12px 10px;vertical-align:middle;'><strong>{escape(course_count_value)}</strong></td></tr>"
            "</tbody>"
            "</table>"
            "<table class='quote-table' border='1' cellspacing='0' cellpadding='10' width='100%' "
            "style='width:100%;border-collapse:collapse;border-spacing:0;margin:0;font-size:11px;'>"
            "<tbody>"
            "<tr>"
            "<td bgcolor='#EEF3FC' width='22%' "
            f"style='background-color:#EEF3FC;color:#111827;border:1px solid #c2ccda;padding:10px;text-align:left;font-weight:700;'>{escape(_quote_doc_text('table_semester', language=language))}</td>"
            "<td bgcolor='#EEF3FC' width='24%' "
            f"style='background-color:#EEF3FC;color:#111827;border:1px solid #c2ccda;padding:10px;text-align:left;font-weight:700;'>{escape(_quote_doc_text('table_month', language=language))}</td>"
            "<td bgcolor='#EEF3FC' "
            f"style='background-color:#EEF3FC;color:#111827;border:1px solid #c2ccda;padding:10px;text-align:left;font-weight:700;'>{escape(_quote_doc_text('calendar_course_dates', language=language))}</td>"
            "</tr>"
            f"{semesters_html}"
            "</tbody>"
            "</table>"
            "</div>"
            "</div>"
        )

    return "".join(blocks), len(grouped)


def _table_html(headers: list[str], rows: list[list[Any]], *, empty_label: str) -> str:
    if not rows:
        return ""

    def _cell_html(value: Any) -> str:
        if isinstance(value, dict):
            raw_html = value.get("html")
            if raw_html is not None:
                return str(raw_html)
            if "text" in value:
                return escape(str(value.get("text") or ""))
        return escape(str(value if value is not None else "-"))

    head = "".join(
        "<th bgcolor='#E7EDF7' "
        "style='background-color:#E7EDF7;color:#111827;border:1px solid #c2ccda;padding:12px 10px 12px 10px;padding-top:12px;padding-right:10px;padding-bottom:12px;padding-left:10px;text-align:left;font-weight:700;line-height:1.4;vertical-align:middle;height:auto;white-space:nowrap;word-break:normal;overflow-wrap:normal;'>"
        f"{escape(cell)}"
        "</th>"
        for cell in headers
    )
    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>"
            + "".join(
                "<td valign='middle' style='border:1px solid #d8dee7;padding:12px 10px 12px 10px;padding-top:12px;padding-right:10px;padding-bottom:12px;padding-left:10px;vertical-align:middle;color:#111827;line-height:1.45;height:auto;white-space:normal;word-break:normal;overflow-wrap:break-word;'>"
                f"{_cell_html(cell)}"
                "</td>"
                for cell in row
            )
            + "</tr>"
        )
    body = "".join(body_rows)
    return (
        "<table class='quote-table' border='1' cellspacing='0' cellpadding='10' width='100%' "
        "style='width:100%;border-collapse:collapse;border-spacing:0;margin:6px 0 10px 0;font-size:11px;table-layout:auto;'>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
    )


def _section_html(title: str, content_html: str, *, level: int = 2) -> str:
    content = str(content_html or "").strip()
    if not content:
        return ""
    tag = "h3" if level == 3 else "h2"
    return f"<{tag}>{escape(title)}</{tag}>{content}"


def _pass_recup_compact_notice_markup(*, language: str | None = None, pdf_compatible: bool = False) -> str:
    title = escape(_quote_doc_text("pass_recup_option_not_subscribed", language=language))
    compact_text = escape(_quote_doc_text("pass_recup_compact_text", language=language))
    compact_limit = escape(_quote_doc_text("pass_recup_compact_limit", language=language))
    if pdf_compatible:
        return (
            f"<p><b>{title}</b>"
            "<br/><font size='9' color='#667085'><i>"
            f"{compact_text}"
            f"<br/>&bull; {compact_limit}"
            "</i></font></p>"
        )
    return (
        f"<p><strong>{title}</strong>"
        "<br/><span class='quote-small-muted'><i>"
        f"{compact_text}"
        f"<br/>&bull; {compact_limit}"
        "</i></span></p>"
    )


def _weekday_label(value: Any, *, language: str | None = None) -> str:
    try:
        day = int(value)
    except (TypeError, ValueError):
        return "-"
    if day < 0 or day > 6:
        return "-"
    return _quote_doc_text(f"weekday_{day}", language=language)


def _parse_hhmm_to_minutes(value: Any) -> int | None:
    raw = str(value or "").strip()
    parsed = re.match(r"^(\d{2}):(\d{2})$", raw)
    if parsed is None:
        return None
    hours = int(parsed.group(1))
    minutes = int(parsed.group(2))
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        return None
    return hours * 60 + minutes


def _duration_label(*, start_time: Any, end_time: Any, fallback_minutes: Any) -> str:
    try:
        fallback = int(fallback_minutes)
    except (TypeError, ValueError):
        fallback = 0
    if fallback > 0:
        return f"{fallback} min"
    start_minutes = _parse_hhmm_to_minutes(start_time)
    end_minutes = _parse_hhmm_to_minutes(end_time)
    if start_minutes is None or end_minutes is None:
        return "-"
    delta = end_minutes - start_minutes
    if delta <= 0:
        delta += 24 * 60
    return f"{delta} min"


def _modality_label(value: Any, *, language: str | None = None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return _quote_doc_text("modality_default", language=language)
    mapping = {
        "ONLINE": _quote_doc_text("modality_online", language=language),
        "ONSITE": _quote_doc_text("modality_onsite", language=language),
        "HYBRID": _quote_doc_text("modality_hybrid", language=language),
    }
    return mapping.get(raw.upper(), raw)


def _parse_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _parse_iso_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _parse_iso_date_set(value: Any) -> set[date]:
    out: set[date] = set()
    for item in _json_list(value):
        parsed = _parse_iso_date(item)
        if parsed is not None:
            out.add(parsed)
    return out


def _school_year_bounds_from_label(label: str | None) -> tuple[date, date] | None:
    normalized = (label or "").strip()
    match = re.fullmatch(r"(\d{4})\s*[-/]\s*(\d{4})", normalized)
    if match is None:
        return None
    start_year = int(match.group(1))
    end_year = int(match.group(2))
    if end_year < start_year:
        return None
    return date(start_year, 9, 1), date(end_year, 8, 31)


def _safe_zoneinfo(value: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(value or "Europe/Paris")
    except Exception:
        return ZoneInfo("Europe/Paris")


def _parse_planning_time(value: Any) -> time | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:5], "%H:%M").time()
    except ValueError:
        return None


def _course_type_modality(activity: CourseType, location: Location) -> str:
    mode = getattr(activity.mode, "value", activity.mode)
    normalized = str(mode or "").strip().upper()
    if normalized in {"ONLINE", "ONSITE"}:
        return normalized
    return "ONLINE" if bool(location.is_online) else "ONSITE"


def _is_synthetic_email(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return normalized.endswith("@piano-academie.invalid") or normalized.endswith("@no-email.local")


def _public_email(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not normalized or _is_synthetic_email(normalized):
        return ""
    return normalized


def _block_is_online(block: dict[str, Any]) -> bool:
    haystack = unicodedata.normalize(
        "NFKD",
        " ".join(str(block.get(key) or "") for key in ("modality", "location_label", "activity_label")),
    ).encode("ascii", "ignore").decode("ascii").lower()
    return "online" in haystack or "ligne" in haystack


def _solfege_mode_semantic(value: Any) -> str:
    normalized = _searchable_text(value)
    if normalized in {"online", "en ligne", "cours en ligne", "mode en ligne"}:
        return "ONLINE"
    if normalized in {"presentiel", "onsite", "cours en presentiel", "mode presentiel"}:
        return "ONSITE"
    if normalized in {"hybride", "hybrid"}:
        return "HYBRID"
    return normalized


def _session_snapshot_matches_block(session: dict[str, Any], block: dict[str, Any]) -> bool:
    activity_id = str(block.get("activity_id") or "").strip()
    start_time = str(block.get("start_time") or "").strip()
    if activity_id and str(session.get("activity_id") or "").strip() != activity_id:
        return False
    if start_time and str(session.get("start_time") or "").strip() != start_time:
        return False
    try:
        block_weekday = int(block.get("weekday"))
    except (TypeError, ValueError):
        block_weekday = -1
    if block_weekday >= 0:
        try:
            session_weekday = int(session.get("weekday"))
        except (TypeError, ValueError):
            session_weekday = -1
        if session_weekday >= 0 and session_weekday != block_weekday:
            return False
    block_location_id = str(block.get("location_id") or "").strip()
    if block_location_id and not _block_is_online(block):
        session_location_id = str(session.get("location_id") or "").strip()
        if session_location_id and session_location_id != block_location_id:
            return False
    return True


def _effective_planning_block_end_date(
    start_date: date,
    end_date: date,
    *,
    session_limit: int,
    school_year_label: str | None,
) -> date:
    return end_date


def _normalized_location_text(value: Any) -> str:
    return (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )


def _school_year_teaching_end_from_label(school_year_label: str | None, location_label: str | None = None) -> date | None:
    if str(school_year_label or "").strip() == "2026-2027":
        normalized_location = _normalized_location_text(location_label)
        if "bar-le-duc" in normalized_location or "bar le duc" in normalized_location:
            return date(2027, 6, 26)
        return date(2027, 6, 19)
    return None


def _school_year_teaching_end_from_block(block: dict[str, Any]) -> date | None:
    school_year_label = str(block.get("school_year_label") or block.get("calendar_school_year") or "")
    location_label = str(block.get("location_label") or "")
    return _school_year_teaching_end_from_label(school_year_label, location_label)


def _expected_sessions_from_planning_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    activity_id = _parse_uuid(block.get("activity_id"))
    start_date = _parse_iso_date(block.get("start_date"))
    end_date = _parse_iso_date(block.get("end_date"))
    start_time = _parse_planning_time(block.get("start_time"))
    end_time = _parse_planning_time(block.get("end_time"))
    if activity_id is None or start_date is None or end_date is None or start_time is None or end_time is None:
        return []
    if bool(block.get("selection_pending")) or end_time <= start_time:
        return []
    try:
        weekday = int(block.get("weekday"))
    except (TypeError, ValueError):
        return []
    if weekday < 0 or weekday > 6:
        return []
    session_limit = _planning_session_limit_from_block(block) or 0
    effective_end_date = _effective_planning_block_end_date(
        start_date,
        end_date,
        session_limit=session_limit,
        school_year_label=str(block.get("school_year_label") or block.get("calendar_school_year") or ""),
    )
    school_year_bounds = _school_year_bounds_from_label(str(block.get("school_year_label") or block.get("calendar_school_year") or ""))
    if session_limit > 0:
        effective_end_date = school_year_bounds[1] if school_year_bounds is not None else start_date + timedelta(days=370)
    teaching_end_date = _school_year_teaching_end_from_block(block)
    if teaching_end_date is not None:
        effective_end_date = min(effective_end_date, teaching_end_date)
    location_id = _parse_uuid(block.get("location_id"))
    snapshot = generate_calendar_snapshot(
        CalendarGenerationInput(
            start_date=start_date,
            end_date=effective_end_date,
            weekdays=[weekday],
            start_time=start_time,
            end_time=end_time,
            recurrence_frequency=str(block.get("recurrence_frequency") or "weekly"),
            activity_id=activity_id,
            location_id=location_id,
            modality=str(block.get("modality") or "") or None,
            holiday_dates=sorted(_parse_iso_date_set(block.get("holiday_dates"))),
            closure_dates=sorted(_parse_iso_date_set(block.get("closure_dates"))),
            session_limit=session_limit if session_limit > 0 else None,
        )
    )
    activity_label = str(block.get("activity_label") or "").strip()
    location_label = str(block.get("location_label") or "").strip()
    weekday_label = str(block.get("weekday_label") or "").strip() or DAY_LABELS_FR.get(weekday, "")
    recommendation_key = str(block.get("recommendation_key") or "").strip()
    series_key = str(block.get("series_key") or "").strip()
    rows: list[dict[str, Any]] = []
    for raw_session in _json_list(snapshot.get("sessions")):
        if not isinstance(raw_session, dict):
            continue
        row = dict(raw_session)
        row.update(
            {
                "activity_label": activity_label,
                "location_label": location_label,
                "weekday": weekday,
                "weekday_label": weekday_label,
            }
        )
        if recommendation_key:
            row["recommendation_key"] = recommendation_key
        if series_key:
            row["series_key"] = series_key
        rows.append(row)
    return rows


def _sessions_from_planning_block(db: Session, block: dict[str, Any]) -> list[dict[str, Any]]:
    activity_id = _parse_uuid(block.get("activity_id"))
    if activity_id is None:
        return []
    start_date = _parse_iso_date(block.get("start_date"))
    end_date = _parse_iso_date(block.get("end_date"))
    if start_date is None or end_date is None:
        return []
    session_limit = _planning_session_limit_from_block(block) or 0
    effective_end_date = _effective_planning_block_end_date(
        start_date,
        end_date,
        session_limit=session_limit,
        school_year_label=str(block.get("school_year_label") or block.get("calendar_school_year") or ""),
    )
    school_year_bounds = _school_year_bounds_from_label(str(block.get("school_year_label") or block.get("calendar_school_year") or ""))
    teaching_end_date = _school_year_teaching_end_from_block(block)
    is_live_planning_block = str(block.get("source") or "").strip() == "live_planning"
    if teaching_end_date is not None:
        effective_end_date = min(effective_end_date, teaching_end_date)
    if is_live_planning_block and school_year_bounds is not None:
        query_end_date = min(teaching_end_date or school_year_bounds[1], school_year_bounds[1])
    elif session_limit > 0:
        query_end_date = school_year_bounds[1] if school_year_bounds is not None else start_date + timedelta(days=370)
        if teaching_end_date is not None:
            query_end_date = min(query_end_date, teaching_end_date)
    else:
        query_end_date = effective_end_date
    start_time = str(block.get("start_time") or "").strip()
    if not start_time:
        return []
    try:
        weekday = int(block.get("weekday"))
    except (TypeError, ValueError):
        weekday = -1
    location_id = _parse_uuid(block.get("location_id"))
    enforce_location = location_id is not None and not _block_is_online(block)
    excluded_dates = _parse_iso_date_set(block.get("holiday_dates")) | _parse_iso_date_set(block.get("closure_dates"))

    lower_bound = datetime.combine(start_date - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    upper_bound = datetime.combine(query_end_date + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)
    conditions = [
        CourseSession.course_type_id == activity_id,
        CourseSession.status == SessionStatus.SCHEDULED,
        CourseSession.start_at_utc >= lower_bound,
        CourseSession.start_at_utc < upper_bound,
    ]
    if enforce_location:
        conditions.append(CourseSession.location_id == location_id)
    series_key = str(block.get("series_key") or "").strip()

    rows = db.execute(
        select(CourseSession, CourseType, Location)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(*conditions)
        .order_by(CourseSession.start_at_utc.asc())
    ).all()
    def collect_sessions(*, enforce_series_key: bool, max_date: date) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for session_obj, activity, location in rows:
            row_series_key = str(session_obj.recurrence_group_id or session_obj.id)
            if enforce_series_key and series_key and row_series_key != series_key:
                continue
            zone = _safe_zoneinfo(session_obj.timezone or location.timezone)
            local_start = session_obj.start_at_utc.astimezone(zone)
            local_end = session_obj.end_at_utc.astimezone(zone)
            if local_start.date() < start_date or local_start.date() > max_date:
                continue
            if local_start.date() in excluded_dates:
                continue
            if weekday >= 0 and local_start.weekday() != weekday:
                continue
            if local_start.strftime("%H:%M") != start_time:
                continue
            key = (
                local_start.date().isoformat(),
                local_start.strftime("%H:%M"),
                str(activity.id),
                str(location.id),
            )
            if key in seen:
                continue
            seen.add(key)
            modality = _course_type_modality(activity, location)
            out.append(
                {
                    "date": local_start.date().isoformat(),
                    "start_time": local_start.strftime("%H:%M"),
                    "end_time": local_end.strftime("%H:%M"),
                    "duration_minutes": int((local_end - local_start).total_seconds() // 60),
                    "activity_id": str(activity.id),
                    "activity_label": activity.name,
                    "location_id": str(location.id),
                    "location_label": location.name,
                    "recommendation_key": block.get("recommendation_key") or None,
                    "series_key": str(session_obj.recurrence_group_id or session_obj.id),
                    "weekday": local_start.weekday(),
                    "weekday_label": DAY_LABELS_FR.get(local_start.weekday(), local_start.strftime("%A")),
                    "modality": modality,
                }
            )
        return out

    limited_series_end_date = query_end_date if session_limit > 0 or is_live_planning_block else effective_end_date
    sessions = collect_sessions(enforce_series_key=True, max_date=limited_series_end_date)
    if is_live_planning_block:
        widened_sessions = collect_sessions(enforce_series_key=False, max_date=query_end_date)
        if len(widened_sessions) > len(sessions):
            sessions = widened_sessions
    elif session_limit > 0 and series_key and len(sessions) < session_limit:
        widened_sessions = collect_sessions(enforce_series_key=False, max_date=query_end_date)
        if len(widened_sessions) > len(sessions):
            sessions = widened_sessions
    sessions, _ = _filter_sessions_blocked_by_quote_school_calendar(db, sessions)
    if session_limit > 0 and len(sessions) < session_limit:
        expected_sessions = _expected_sessions_from_planning_block(block)
        expected_sessions, _ = _filter_sessions_blocked_by_quote_school_calendar(db, expected_sessions)
        if len(expected_sessions) > len(sessions):
            sessions = expected_sessions
    if session_limit > 0:
        sessions = sessions[:session_limit]
    return sessions


def _selected_solfege_live_series_for_slot(
    db: Session | None,
    *,
    activity_id: UUID,
    selected_slot: dict[str, Any],
    school_year_label: str | None,
) -> tuple[list[tuple[CourseSession, CourseType, Location]], Location | None]:
    if db is None:
        return [], None
    bounds = _school_year_bounds_from_label(school_year_label)
    if bounds is None:
        return [], None
    try:
        selected_weekday = int(selected_slot.get("weekday"))
    except (TypeError, ValueError):
        return [], None
    if selected_weekday < 0 or selected_weekday > 6:
        return [], None
    selected_start_time = str(selected_slot.get("start_time") or selected_slot.get("start") or "").strip()
    selected_end_time = str(selected_slot.get("end_time") or selected_slot.get("end") or "").strip()
    if not selected_start_time or not selected_end_time:
        return [], None

    selected_location_id = _parse_uuid(selected_slot.get("location_id"))
    selected_modality = _solfege_mode_semantic(
        selected_slot.get("modality") or selected_slot.get("location_label") or selected_slot.get("mode")
    )
    lower_bound = datetime.combine(bounds[0] - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    upper_bound = datetime.combine(bounds[1] + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)
    rows = db.execute(
        select(CourseSession, CourseType, Location)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(
            CourseSession.course_type_id == activity_id,
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= lower_bound,
            CourseSession.start_at_utc < upper_bound,
        )
        .order_by(CourseSession.start_at_utc.asc())
    ).all()

    grouped: dict[str, list[tuple[CourseSession, CourseType, Location]]] = {}
    locations_by_group: dict[str, Location] = {}
    for session_obj, activity, location in rows:
        zone = _safe_zoneinfo(session_obj.timezone or location.timezone)
        local_start = session_obj.start_at_utc.astimezone(zone)
        local_end = session_obj.end_at_utc.astimezone(zone)
        if local_start.date() < bounds[0] or local_start.date() > bounds[1]:
            continue
        if local_start.weekday() != selected_weekday:
            continue
        if local_start.strftime("%H:%M") != selected_start_time or local_end.strftime("%H:%M") != selected_end_time:
            continue
        if selected_location_id is not None:
            if session_obj.location_id != selected_location_id:
                continue
        else:
            session_location_semantic = _solfege_mode_semantic(location.name)
            course_modality = _course_type_modality(activity, location)
            if selected_modality == "ONLINE" and course_modality != "ONLINE" and session_location_semantic != "ONLINE":
                continue
            if selected_modality == "ONSITE" and (course_modality == "ONLINE" or session_location_semantic == "ONLINE"):
                continue

        group_key = str(session_obj.recurrence_group_id or session_obj.id)
        grouped.setdefault(group_key, []).append((session_obj, activity, location))
        locations_by_group.setdefault(group_key, location)

    if not grouped:
        return [], None
    best_key = max(grouped, key=lambda key: len(grouped[key]))
    return sorted(grouped[best_key], key=lambda row: row[0].start_at_utc), locations_by_group.get(best_key)


def _session_snapshot_from_live_row(
    session_obj: CourseSession,
    activity: CourseType,
    location: Location,
    *,
    recommendation_key: str,
) -> dict[str, Any]:
    zone = _safe_zoneinfo(session_obj.timezone or location.timezone)
    local_start = session_obj.start_at_utc.astimezone(zone)
    local_end = session_obj.end_at_utc.astimezone(zone)
    return {
        "date": local_start.date().isoformat(),
        "start_time": local_start.strftime("%H:%M"),
        "end_time": local_end.strftime("%H:%M"),
        "duration_minutes": int((local_end - local_start).total_seconds() // 60),
        "activity_id": str(activity.id),
        "activity_label": activity.name,
        "location_id": str(location.id),
        "location_label": location.name,
        "recommendation_key": recommendation_key,
        "series_key": str(session_obj.recurrence_group_id or session_obj.id),
        "weekday": local_start.weekday(),
        "weekday_label": DAY_LABELS_FR.get(local_start.weekday(), local_start.strftime("%A")),
        "modality": _course_type_modality(activity, location),
    }


def _calendar_session_dedupe_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("date") or ""),
        str(item.get("start_time") or ""),
        str(item.get("activity_id") or ""),
        str(item.get("location_id") or ""),
    )


def _dedupe_calendar_sessions(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    changed = False
    for item in items:
        key = _calendar_session_dedupe_key(item)
        if key in seen:
            changed = True
            continue
        seen.add(key)
        deduped.append(item)
    return deduped, changed


def _calendar_session_matches_planning_block(
    session: dict[str, Any],
    block: dict[str, Any],
    *,
    refreshed_dates: set[str],
) -> bool:
    session_date = str(session.get("date") or "").strip()
    if session_date not in refreshed_dates:
        return False
    if str(session.get("activity_id") or "").strip() != str(block.get("activity_id") or "").strip():
        return False

    block_location_id = str(block.get("location_id") or "").strip()
    if block_location_id and str(session.get("location_id") or "").strip() != block_location_id:
        return False

    block_series_key = str(block.get("series_key") or "").strip()
    if block_series_key:
        return str(session.get("series_key") or "").strip() == block_series_key

    block_recommendation_key = str(block.get("recommendation_key") or "").strip()
    if block_recommendation_key:
        return str(session.get("recommendation_key") or "").strip() == block_recommendation_key

    return True


def _quote_school_calendar_rows(db: Session) -> list[dict[str, Any]]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_SCHOOL_CALENDARS_SETTING_KEY))
    if setting is None:
        return []
    try:
        parsed = json.loads(setting.value or "[]")
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict) and _is_true(item.get("is_active", True))]


def _calendar_row_location_ids(row: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    location_id = _parse_uuid(row.get("location_id"))
    if location_id is not None:
        out.add(str(location_id))
    for item in _json_list(row.get("location_ids")):
        parsed = _parse_uuid(item)
        if parsed is not None:
            out.add(str(parsed))
    return out


def _calendar_row_applies_to_session(row: dict[str, Any], *, location_id: str, session_date: date) -> bool:
    location_ids = _calendar_row_location_ids(row)
    if location_ids and location_id not in location_ids:
        return False
    bounds = _school_year_bounds_from_label(str(row.get("school_year_label") or ""))
    if bounds is not None and not (bounds[0] <= session_date <= bounds[1]):
        return False
    return True


def _expand_calendar_vacation_dates(row: dict[str, Any]) -> set[date]:
    out: set[date] = set()
    for raw_period in _json_list(row.get("vacation_periods")):
        if not isinstance(raw_period, dict):
            continue
        start = _parse_iso_date(raw_period.get("start_date"))
        end = _parse_iso_date(raw_period.get("end_date"))
        if start is None or end is None or end < start:
            continue
        current = start
        while current <= end:
            out.add(current)
            current += timedelta(days=1)
    return out


def _session_blocked_by_quote_school_calendar(
    *,
    session: dict[str, Any],
    calendar_rows: list[dict[str, Any]],
    activity_exclusion_flags: dict[str, tuple[bool, bool]],
) -> bool:
    session_date = _parse_iso_date(session.get("date"))
    activity_id = str(session.get("activity_id") or "").strip()
    location_id = str(session.get("location_id") or "").strip()
    if session_date is None or not activity_id or not location_id:
        return False

    include_holidays, include_school_vacations = activity_exclusion_flags.get(activity_id, (True, True))
    if not include_holidays and not include_school_vacations:
        return False

    for row in calendar_rows:
        if not _calendar_row_applies_to_session(row, location_id=location_id, session_date=session_date):
            continue
        if include_holidays and session_date in _parse_iso_date_set(row.get("holiday_dates")):
            return True
        if include_school_vacations and (
            session_date in _parse_iso_date_set(row.get("closure_dates"))
            or session_date in _expand_calendar_vacation_dates(row)
        ):
            return True
    return False


def _filter_sessions_blocked_by_quote_school_calendar(
    db: Session,
    sessions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    if not sessions:
        return sessions, False
    calendar_rows = _quote_school_calendar_rows(db)
    if not calendar_rows:
        return sessions, False

    activity_ids = {
        parsed
        for parsed in (_parse_uuid(item.get("activity_id")) for item in sessions)
        if parsed is not None
    }
    rows = db.scalars(select(CourseType).where(CourseType.id.in_(activity_ids))).all() if activity_ids else []
    activity_exclusion_flags = {
        str(row.id): (
            bool(getattr(row, "exclude_holidays_in_recurrence", True)),
            bool(getattr(row, "exclude_school_vacations_in_recurrence", True)),
        )
        for row in rows
    }
    filtered = [
        item
        for item in sessions
        if not _session_blocked_by_quote_school_calendar(
            session=item,
            calendar_rows=calendar_rows,
            activity_exclusion_flags=activity_exclusion_flags,
        )
    ]
    return filtered, len(filtered) != len(sessions)


def _quote_line_recommendation_key(line: QuoteLine, *, force_line_key: bool = False) -> str:
    activity_id = str(getattr(line, "activity_id", None) or "").strip()
    if not activity_id:
        return ""
    line_meta = _json_object(getattr(line, "meta", None))
    source = str(line_meta.get("typeform_automatic_line") or "").strip()
    if source:
        return f"{activity_id}:{source}"
    if force_line_key:
        line_id = str(getattr(line, "id", None) or "").strip()
        if line_id:
            return f"{activity_id}:line:{line_id}"
    return activity_id


def _planning_session_limit_from_quote_line_meta(line: QuoteLine | None) -> int | None:
    if line is None:
        return None
    line_meta = _json_object(getattr(line, "meta", None))
    template = _json_object(line_meta.get("typeform_template"))
    raw_limit = line_meta.get("planning_session_limit")
    if raw_limit is None:
        raw_limit = template.get("planning_session_limit")
    if raw_limit is None:
        line_category = str(getattr(line, "line_category", "") or "").strip().lower()
        pricing_unit = str(getattr(line, "pricing_unit", "") or "").strip().lower()
        if (
            getattr(line, "activity_id", None) is not None
            and (line_category == "service" or pricing_unit in {"session", "per_session"})
        ):
            quantity = _decimal_from_any(getattr(line, "quantity", None), Decimal("0"))
            if quantity > Decimal("1") and quantity == quantity.to_integral_value():
                raw_limit = int(quantity)
    try:
        limit = int(str(raw_limit).strip())
    except (TypeError, ValueError):
        return None
    return limit if limit > 0 else None


def _planning_session_limit_from_block(block: dict[str, Any]) -> int | None:
    try:
        limit = int(str(block.get("planning_session_limit") or "").strip())
    except (TypeError, ValueError):
        return None
    return limit if limit > 1 else None


def _calendar_snapshot_with_line_recommendation_keys(
    db: Session | None,
    calendar_snapshot: dict[str, Any],
    *,
    lines: list[QuoteLine],
) -> dict[str, Any]:
    snapshot = dict(_json_object(calendar_snapshot))
    blocks = [dict(item) for item in _json_list(snapshot.get("blocks")) if isinstance(item, dict)]
    if not blocks:
        return snapshot

    lines_by_activity_id: dict[str, list[QuoteLine]] = {}
    ordered_lines = sorted(
        lines,
        key=lambda line: (
            int(getattr(line, "sort_order", None) or 0),
            getattr(line, "created_at", None) or datetime.min.replace(tzinfo=timezone.utc),
            str(getattr(line, "id", "") or ""),
        ),
    )
    for line in ordered_lines:
        activity_id = str(getattr(line, "activity_id", None) or "").strip()
        if not activity_id or _line_matches_solfege_activity(line):
            continue
        lines_by_activity_id.setdefault(activity_id, []).append(line)
    lines_by_recommendation_key = {
        key: line
        for activity_lines in lines_by_activity_id.values()
        for line in activity_lines
        if (key := _quote_line_recommendation_key(line, force_line_key=len(activity_lines) > 1))
    }

    target_activity_ids = {
        activity_id
        for activity_id, activity_lines in lines_by_activity_id.items()
        if len(activity_lines) > 1
        or any(str(_json_object(getattr(line, "meta", None)).get("typeform_automatic_line") or "").strip() for line in activity_lines)
        or any(_planning_session_limit_from_quote_line_meta(line) is not None for line in activity_lines)
    }
    if not target_activity_ids:
        return snapshot

    cursors: dict[str, int] = {}
    changed_blocks = False
    normalized_blocks: list[dict[str, Any]] = []
    for block in blocks:
        activity_id = str(block.get("activity_id") or "").strip()
        if activity_id not in target_activity_ids:
            normalized_blocks.append(block)
            continue

        activity_lines = lines_by_activity_id.get(activity_id) or []
        existing_key = str(block.get("recommendation_key") or "").strip()
        should_reassign_duplicate_line_key = (
            len(activity_lines) > 1
            and (
                not existing_key
                or ":line:" in existing_key
                or existing_key not in lines_by_recommendation_key
            )
        )
        if existing_key and existing_key != activity_id and not should_reassign_duplicate_line_key:
            matching_line = lines_by_recommendation_key.get(existing_key)
            limit = _planning_session_limit_from_quote_line_meta(matching_line)
            if limit is not None and _planning_session_limit_from_block(block) != limit:
                block = {**block, "planning_session_limit": limit}
                changed_blocks = True
            normalized_blocks.append(block)
            continue

        cursor = cursors.get(activity_id, 0)
        line = activity_lines[min(cursor, len(activity_lines) - 1)] if activity_lines else None
        cursors[activity_id] = cursor + 1
        recommendation_key = (
            _quote_line_recommendation_key(line, force_line_key=len(activity_lines) > 1)
            if line is not None
            else activity_id
        )
        if recommendation_key and recommendation_key != existing_key:
            block = {**block, "recommendation_key": recommendation_key}
            changed_blocks = True
        limit = _planning_session_limit_from_quote_line_meta(line)
        if limit is not None and _planning_session_limit_from_block(block) != limit:
            block = {**block, "planning_session_limit": limit}
            changed_blocks = True
        normalized_blocks.append(block)

    if not changed_blocks:
        snapshot["blocks"] = normalized_blocks
        return snapshot

    snapshot["blocks"] = normalized_blocks
    if db is None:
        return snapshot

    refreshed_sessions: list[dict[str, Any]] = []
    for raw_session in _json_list(snapshot.get("sessions")):
        if not isinstance(raw_session, dict):
            continue
        if str(raw_session.get("activity_id") or "").strip() in target_activity_ids:
            continue
        refreshed_sessions.append(dict(raw_session))

    for block in normalized_blocks:
        if str(block.get("activity_id") or "").strip() not in target_activity_ids:
            continue
        refreshed_sessions.extend(_sessions_from_planning_block(db, block))

    refreshed_sessions, _ = _dedupe_calendar_sessions(refreshed_sessions)
    refreshed_sessions.sort(
        key=lambda item: (
            str(item.get("date") or ""),
            str(item.get("start_time") or ""),
            str(item.get("activity_label") or ""),
        )
    )
    snapshot["sessions"] = refreshed_sessions
    snapshot["sessions_count"] = len(refreshed_sessions)
    return snapshot


def _calendar_snapshot_with_planning_sessions(db: Session | None, calendar_snapshot: dict[str, Any]) -> dict[str, Any]:
    snapshot = dict(_json_object(calendar_snapshot))
    if db is None:
        return snapshot
    sessions, deduped_existing = _dedupe_calendar_sessions(
        [dict(item) for item in _json_list(snapshot.get("sessions")) if isinstance(item, dict)]
    )
    blocks = [dict(item) for item in _json_list(snapshot.get("blocks")) if isinstance(item, dict)]
    changed = deduped_existing
    seen: set[tuple[str, str, str, str]] = {_calendar_session_dedupe_key(item) for item in sessions}
    for block in blocks:
        refreshed_block_sessions = _sessions_from_planning_block(db, block)
        if refreshed_block_sessions:
            refreshed_dates = {str(item.get("date") or "").strip() for item in refreshed_block_sessions}
            kept_sessions = [
                item
                for item in sessions
                if not _calendar_session_matches_planning_block(item, block, refreshed_dates=refreshed_dates)
            ]
            if len(kept_sessions) != len(sessions):
                sessions = kept_sessions
                seen = {_calendar_session_dedupe_key(item) for item in sessions}
                changed = True
            last_refreshed_date = str(refreshed_block_sessions[-1].get("date") or "").strip()
            if last_refreshed_date and str(block.get("end_date") or "").strip() != last_refreshed_date:
                block["end_date"] = last_refreshed_date
                changed = True
        for item in refreshed_block_sessions:
            key = _calendar_session_dedupe_key(item)
            if key in seen:
                continue
            seen.add(key)
            sessions.append(item)
            changed = True
    sessions, filtered_by_school_calendar = _filter_sessions_blocked_by_quote_school_calendar(db, sessions)
    changed = changed or filtered_by_school_calendar
    if changed:
        sessions.sort(
            key=lambda item: (
                str(item.get("date") or ""),
                str(item.get("start_time") or ""),
                str(item.get("activity_label") or ""),
            )
        )
        snapshot["sessions"] = sessions
        snapshot["sessions_count"] = len(sessions)
        snapshot["blocks"] = blocks
    return snapshot


def _slot_mode_label(value: Any, *, language: str | None = None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    mapping = {
        "ONLINE": _quote_doc_text("slot_mode_online", language=language),
        "ONSITE": _quote_doc_text("slot_mode_onsite", language=language),
        "HYBRID": _quote_doc_text("slot_mode_hybrid", language=language),
        "ANY": "",
    }
    return mapping.get(raw.upper(), "")


def _extract_slot_label_parts(value: Any, *, language: str | None = None) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    cleaned_parts: list[str] = []
    mode_label = ""
    for part in raw.split("·"):
        text = " ".join(part.strip().split())
        if not text:
            continue
        normalized = text.casefold()
        upper = text.upper()
        if upper == "ANY":
            continue
        if normalized in {
            "online",
            "en ligne",
            "cours en ligne",
            "mode : cours en ligne",
            "mode: cours en ligne",
            "mode : en ligne",
            "mode: en ligne",
        }:
            mode_label = _quote_doc_text("slot_mode_online", language=language)
            continue
        if normalized in {
            "onsite",
            "présentiel",
            "presentiel",
            "cours en présentiel",
            "cours en presentiel",
            "mode : cours en présentiel",
            "mode : cours en presentiel",
            "mode: cours en présentiel",
            "mode: cours en presentiel",
        }:
            mode_label = _quote_doc_text("slot_mode_onsite", language=language)
            continue
        if normalized in {
            "hybrid",
            "hybride",
            "mode : cours en présentiel ou en ligne",
            "mode: cours en présentiel ou en ligne",
        }:
            mode_label = _quote_doc_text("slot_mode_hybrid", language=language)
            continue
        cleaned_parts.append(text)
    return " · ".join(cleaned_parts), mode_label


def _sanitize_slot_label_text(value: Any, *, language: str | None = None) -> str:
    cleaned_label, mode_label = _extract_slot_label_parts(value, language=language)
    if cleaned_label and mode_label:
        return f"{cleaned_label} · {mode_label}"
    return cleaned_label or mode_label or str(value or "").strip()


def _replace_word_preserving_case(value: str, pattern: str, replacement: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        matched = match.group(0)
        if matched.isupper():
            return replacement.upper()
        if matched[:1].isupper():
            return replacement.capitalize()
        return replacement

    return re.sub(pattern, _repl, value, flags=re.IGNORECASE)


def _harmonize_display_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    text = _replace_word_preserving_case(text, r"\bsolfege\b", "solfège")
    text = _replace_word_preserving_case(text, r"\bpresentiel\b", "présentiel")
    text = _replace_word_preserving_case(text, r"\bcontrole\b", "contrôle")
    return text


def _searchable_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


ENGLISH_BUSINESS_LABELS = {
    "cours collectifs ado/adultes": "Teen/adult group lessons",
    "cours collectif ado/adulte": "Teen/adult group lesson",
    "cours collectifs ado adultes": "Teen/adult group lessons",
    "cours collectif ado adulte": "Teen/adult group lesson",
    "cours collectifs adolescents/adultes": "Teen/adult group lessons",
    "cours collectif adolescent/adulte": "Teen/adult group lesson",
    "cours collectifs enfants": "Children's group lessons",
    "cours collectif enfant": "Children's group lesson",
    "eveil musical": "Early music discovery",
    "éveil musical": "Early music discovery",
    "initiation au piano": "Piano initiation",
    "cours de solfege": "Music theory lesson",
    "cours de solfege en ligne": "Online music theory lesson",
    "solfege": "Music theory",
}

ENGLISH_CATALOG_LABELS = {
    "cahier de solfege de niveau 1": "Music theory workbook - Level 1",
    "cahier de solfege de niveau 2": "Music theory workbook - Level 2",
    "cahier de solfege de niveau 3": "Music theory workbook - Level 3",
    "cahier de solfege de niveau 4": "Music theory workbook - Level 4",
    "cahier de solfege de niveau 5": "Music theory workbook - Level 5",
    "partitions ados": "Teen sheet music",
    "partitions ado": "Teen sheet music",
    "kit ado": "Teen kit",
    "kit ados": "Teen kit",
    "kit adulte": "Adult kit",
    "kit adultes": "Adult kit",
    "kit enfant": "Children's kit",
    "kit enfants": "Children's kit",
    "frais de dossier": "Enrollment fee",
    "cours de controle": "Assessment lesson",
    "cours de controle x 2": "Assessment lessons x 2",
    "avec son cahier de travail": "Includes its workbook",
}

ENGLISH_LOCATION_LABELS = {
    "rue richelieu": "Richelieu Street",
    "rue de richelieu": "Richelieu Street",
    "richelieu": "Richelieu Street",
    "rue de pompe": "Pompe Street",
    "rue de la pompe": "Pompe Street",
    "pompe": "Pompe Street",
    "rue scheffer": "Scheffer Street",
    "scheffer": "Scheffer Street",
    "rue d'assas": "Assas Street",
    "rue assas": "Assas Street",
    "assas": "Assas Street",
    "rue dulong": "Dulong Street",
    "dulong": "Dulong Street",
    "en ligne": "Online",
}

ENGLISH_WEEKDAY_LABELS = {
    "lundi": "Monday",
    "mardi": "Tuesday",
    "mercredi": "Wednesday",
    "jeudi": "Thursday",
    "vendredi": "Friday",
    "samedi": "Saturday",
    "dimanche": "Sunday",
}

ENGLISH_TEXT_FRAGMENTS = (
    ("Conditions générales de vente et d’inscription", "General terms of sale and enrollment"),
    ("Conditions generales de vente et d’inscription", "General terms of sale and enrollment"),
    ("Conditions générales de vente et d'inscription", "General terms of sale and enrollment"),
    ("Conditions generales de vente et d'inscription", "General terms of sale and enrollment"),
    ("Conditions générales de vente", "Terms and conditions of sale"),
    ("Conditions generales de vente", "Terms and conditions of sale"),
    ("Conditions d’inscription", "Enrollment terms"),
    ("Conditions d'inscription", "Enrollment terms"),
    ("Pour finaliser votre inscription", "To finalize your enrollment"),
)


def _is_english_quote_language(language: str | None) -> bool:
    return _quote_doc_language(language=language).lower().startswith("en")


def _localized_business_label(value: Any, *, language: str | None = None) -> str:
    text = _harmonize_display_text(value)
    if not text or not _is_english_quote_language(language):
        return text
    normalized = _searchable_text(text)
    if normalized in ENGLISH_BUSINESS_LABELS:
        return ENGLISH_BUSINESS_LABELS[normalized]
    for source, replacement in ENGLISH_BUSINESS_LABELS.items():
        if source in {"solfege", "cours de solfege"}:
            continue
        if source in normalized:
            return replacement
    return text


def _localized_catalog_text(value: Any, *, language: str | None = None) -> str:
    text = _harmonize_display_text(value)
    if not text or not _is_english_quote_language(language):
        return text
    normalized = _searchable_text(text)
    if normalized in ENGLISH_CATALOG_LABELS:
        return ENGLISH_CATALOG_LABELS[normalized]

    if "\n" in text:
        return "\n".join(_localized_catalog_text(line, language=language) for line in text.splitlines())

    match = re.fullmatch(r"cahier de solfege de niveau\s+(\d+)", normalized)
    if match:
        return f"Music theory workbook - Level {match.group(1)}"

    match = re.fullmatch(r"solfege\s*-?\s*niveau\s+(\d+)", normalized)
    if match:
        return f"Music theory - Level {match.group(1)}"

    for source, replacement in ENGLISH_CATALOG_LABELS.items():
        text = re.sub(re.escape(source), replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\bcours de contr[oô]le\s*x\s*2\b", "Assessment lessons x 2", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcours de contr[oô]le\b", "Assessment lesson", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[Ss]olfège\b", "Music theory", text)
    return text


def _localized_location_label(value: Any, *, language: str | None = None) -> str:
    text = str(value or "").strip()
    if not text or text == "-" or not _is_english_quote_language(language):
        return text or "-"
    normalized = _searchable_text(text)
    return ENGLISH_LOCATION_LABELS.get(normalized, text)


def _localized_weekday_label(value: Any, *, language: str | None = None) -> str:
    text = str(value or "").strip()
    if not text or text == "-":
        return text or "-"
    if not _is_english_quote_language(language):
        return text
    return ENGLISH_WEEKDAY_LABELS.get(_searchable_text(text), text)


def _weekday_label_from_fields(label_value: Any, weekday_value: Any, *, language: str | None = None) -> str:
    label = str(label_value or "").strip()
    if label:
        return _localized_weekday_label(label, language=language)
    return _weekday_label(weekday_value, language=language)


def _planning_activity_display_label(block: dict[str, Any], *, language: str | None = None) -> str:
    return _localized_business_label(str(block.get("activity_label") or "-").strip() or "-", language=language)


def _quote_line_display_title(line: Any, *, language: str | None = None) -> str:
    title = str(getattr(line, "title", "") or "-").strip() or "-"
    business_label = _localized_business_label(title, language=language)
    return _localized_catalog_text(business_label, language=language)


def _localized_english_text_fragments(value: Any, *, language: str | None = None) -> str:
    text = str(value or "")
    if not text or not _is_english_quote_language(language):
        return text
    for source, replacement in ENGLISH_TEXT_FRAGMENTS:
        text = text.replace(source, replacement)
    return text


def _time_slot_parts(slot: dict[str, Any]) -> tuple[str, str] | None:
    start = str(slot.get("start_time") or slot.get("start") or "").strip()
    end = str(slot.get("end_time") or slot.get("end") or "").strip()
    if not start or not end:
        return None
    return start, end


def _matching_solfege_rule_for_pending_block(
    db: Session | None,
    *,
    level_code: str | None,
    location_id: Any = None,
    modality: Any = None,
) -> SolfegeLevelRule | None:
    normalized_level = str(level_code or "").strip()
    if db is None or not normalized_level:
        return None
    rows = db.scalars(
        select(SolfegeLevelRule)
        .where(
            SolfegeLevelRule.level_code == normalized_level,
            SolfegeLevelRule.is_active.is_(True),
        )
    ).all()
    if not rows:
        return None

    expected_location_id = str(location_id or "").strip() or None
    expected_modality = str(modality or "").strip().upper() or None

    def _score(rule: SolfegeLevelRule) -> tuple[int, int, float]:
        rule_location_id = str(rule.location_id).strip() if rule.location_id else None
        rule_modality = str(rule.modality or "").strip().upper() or None

        if expected_location_id and rule_location_id == expected_location_id:
            location_score = 0
        elif rule_location_id is None:
            location_score = 1
        else:
            location_score = 3

        if expected_modality and rule_modality == expected_modality:
            modality_score = 0
        elif rule_modality is None:
            modality_score = 1
        else:
            modality_score = 3

        created_rank = -(rule.created_at.timestamp() if getattr(rule, "created_at", None) else 0.0)
        return location_score, modality_score, created_rank

    return min(rows, key=_score)


def _solfege_slot_labels_from_rule(
    rule: SolfegeLevelRule | None,
    *,
    location_label: str = "",
    language: str | None = None,
) -> list[str]:
    if rule is None:
        return []

    slot_dicts = [slot for slot in _json_list(rule.allowed_time_slots) if isinstance(slot, dict)]
    if not slot_dicts:
        return []

    labels: list[str] = []
    has_structured_weekdays = any(
        isinstance(slot.get("weekday"), int) and 0 <= int(slot.get("weekday")) <= 6
        for slot in slot_dicts
    )
    weekdays = (
        []
        if has_structured_weekdays
        else [day for day in _json_list(rule.allowed_weekdays) if isinstance(day, int) and 0 <= int(day) <= 6]
    )
    if not has_structured_weekdays and not weekdays:
        weekdays = [0, 1, 2, 3, 4, 5, 6]

    for slot in slot_dicts:
        parts = _time_slot_parts(slot)
        if parts is None:
            continue
        start, end = parts
        slot_weekdays: list[int]
        if has_structured_weekdays:
            weekday = int(slot.get("weekday")) if isinstance(slot.get("weekday"), int) else -1
            if weekday < 0 or weekday > 6:
                continue
            slot_weekdays = [weekday]
        else:
            slot_weekdays = [int(day) for day in weekdays]
        for weekday in slot_weekdays:
            base_label = f"{_weekday_label(weekday, language=language)} {start}-{end}"
            if location_label:
                labels.append(_sanitize_slot_label_text(f"{base_label} · {location_label}", language=language))
            else:
                labels.append(_sanitize_slot_label_text(base_label, language=language))
    return _unique_text_parts(*labels)


def _factorize_slot_labels(labels: list[str], *, language: str | None = None) -> tuple[list[str], str]:
    sanitized_labels = [_sanitize_slot_label_text(item, language=language) for item in labels if str(item or "").strip()]
    if not sanitized_labels:
        return [], ""
    cleaned_labels: list[str] = []
    mode_labels: list[str] = []
    for item in sanitized_labels:
        cleaned_label, mode_label = _extract_slot_label_parts(item, language=language)
        if cleaned_label:
            cleaned_labels.append(cleaned_label)
        elif item:
            cleaned_labels.append(item)
        if mode_label:
            mode_labels.append(mode_label)
    unique_cleaned_labels = list(dict.fromkeys(cleaned_labels))
    unique_mode_labels = list(dict.fromkeys(mode_labels))
    if unique_mode_labels and len(unique_mode_labels) == 1 and len(mode_labels) == len(sanitized_labels):
        return unique_cleaned_labels, unique_mode_labels[0]
    return sanitized_labels, ""


def _slot_label(value: dict[str, Any], *, fallback_location_label: str = "", language: str | None = None) -> str:
    label = _sanitize_slot_label_text(value.get("label"), language=language)
    if label:
        return label
    weekday = _weekday_label_from_fields(value.get("weekday_label"), value.get("weekday"), language=language)
    start = str(value.get("start_time") or value.get("start") or "").strip()
    end = str(value.get("end_time") or value.get("end") or "").strip()
    location_label = _localized_location_label(str(value.get("location_label") or fallback_location_label or "").strip(), language=language)
    modality_label = _slot_mode_label(value.get("modality"), language=language)

    parts: list[str] = []
    if weekday and weekday != "-":
        parts.append(f"{weekday} {start}-{end}".strip() if start and end else weekday)
    elif start and end:
        parts.append(f"{start}-{end}")
    if modality_label:
        parts.append(modality_label)
    if location_label:
        parts.append(location_label)
    return _sanitize_slot_label_text(" · ".join(part for part in parts if part).strip(), language=language) or "-"


def _is_solfege_planning_block(block: dict[str, Any]) -> bool:
    activity_label = str(block.get("activity_label") or "").strip()
    activity_code = str(block.get("activity_code") or block.get("activity_service_code") or "").strip()
    pending_level = str(block.get("pending_solfege_level") or "").strip()
    haystack = _searchable_text(f"{activity_label} {activity_code}")
    return bool(pending_level) or "solfege" in haystack


def _solfege_included_pending_notice_text(*, language: str | None = None) -> str:
    return _quote_doc_text("solfege_pending_notice", language=language)


def _pending_planning_block_display(block: dict[str, Any], *, language: str | None = None) -> tuple[str, str, str, str]:
    if _is_solfege_planning_block(block):
        level_label = str(block.get("pending_solfege_level") or "").strip() or _extract_solfege_level_from_text(
            block.get("activity_label")
        )
        activity_label = _quote_doc_text("course_solfege", language=language)
        if str(block.get("modality") or "").strip().upper() == "ONLINE":
            activity_label = _quote_doc_text("course_solfege_online", language=language)
        if level_label:
            activity_label += f" - {_quote_doc_text('course_solfege_level', language=language, level=level_label)}"
        activity_label += f" ({_quote_doc_text('course_included_quote', language=language)})"
        return activity_label, "-", _quote_doc_text("to_select_short", language=language), "-"
    return (
        _planning_activity_display_label(block, language=language),
        _quote_doc_text("to_select_short", language=language),
        _quote_doc_text("to_select_short", language=language),
        "-",
    )


def _planning_blocks_table_html(
    snapshot: dict[str, Any],
    *,
    selected_solfege_slot: dict[str, Any] | None = None,
    language: str | None = None,
) -> tuple[str, int]:
    blocks = [item for item in _json_list(snapshot.get("blocks")) if isinstance(item, dict)]
    rows: list[list[str]] = []
    normalized_selected_solfege_slot = _json_object(selected_solfege_slot)
    for block in blocks:
        pending_slot_labels: list[str] = []
        for raw_slot in _json_list(block.get("pending_slot_options")):
            if not isinstance(raw_slot, dict):
                continue
            label = _slot_label(raw_slot, fallback_location_label=str(block.get("location_label") or "").strip(), language=language)
            if label:
                pending_slot_labels.append(label)
                continue
            weekday_text = _weekday_label_from_fields(raw_slot.get("weekday_label"), raw_slot.get("weekday"), language=language)
            start = str(raw_slot.get("start_time") or raw_slot.get("start") or "").strip()
            end = str(raw_slot.get("end_time") or raw_slot.get("end") or "").strip()
            if weekday_text and start and end:
                pending_slot_labels.append(f"{weekday_text} {start}-{end}")
        deduped_pending_slots = list(dict.fromkeys(pending_slot_labels))
        try:
            weekday_value = int(block.get("weekday") or -99)
        except (TypeError, ValueError):
            weekday_value = -99
        selection_pending = bool(block.get("selection_pending")) or weekday_value == -1
        activity_label = _planning_activity_display_label(block, language=language)
        activity_type = str(block.get("activity_type_label") or "").strip()
        if not activity_type:
            activity_type = _modality_label(block.get("modality"), language=language)
        activity_type = _harmonize_display_text(activity_type)
        location_label = _localized_location_label(str(block.get("location_label") or "-").strip() or "-", language=language)
        if selection_pending:
            is_solfege_block = _is_solfege_planning_block(block)
            if is_solfege_block and normalized_selected_solfege_slot:
                activity_label, _, _, _ = _pending_planning_block_display(block, language=language)
                weekday = _weekday_label_from_fields(
                    normalized_selected_solfege_slot.get("weekday_label"),
                    normalized_selected_solfege_slot.get("weekday"),
                    language=language,
                )
                start_time = str(normalized_selected_solfege_slot.get("start_time") or normalized_selected_solfege_slot.get("start") or "").strip()
                end_time = str(normalized_selected_solfege_slot.get("end_time") or normalized_selected_solfege_slot.get("end") or "").strip()
                time_range = f"{start_time} - {end_time}" if start_time and end_time else "-"
                duration = _duration_label(
                    start_time=start_time,
                    end_time=end_time,
                    fallback_minutes=normalized_selected_solfege_slot.get("duration_minutes") or block.get("duration_minutes"),
                )
                location_label = _localized_location_label(
                    str(
                        normalized_selected_solfege_slot.get("location_label")
                        or block.get("location_label")
                        or "-"
                    ).strip()
                    or "-",
                    language=language,
                )
                activity_type = _quote_doc_text("course_solfege", language=language)
            else:
                activity_label, weekday, time_range, duration = _pending_planning_block_display(block, language=language)
            if is_solfege_block:
                activity_type = _quote_doc_text("course_solfege", language=language)
            elif deduped_pending_slots:
                time_range = _quote_doc_text("to_select", language=language)
        else:
            weekday = _weekday_label_from_fields(block.get("weekday_label"), block.get("weekday"), language=language)
            start_time = str(block.get("start_time") or "").strip()
            end_time = str(block.get("end_time") or "").strip()
            time_range = f"{start_time} - {end_time}" if start_time and end_time else "-"
            duration = _duration_label(
                start_time=start_time,
                end_time=end_time,
                fallback_minutes=block.get("duration_minutes"),
            )
        rows.append([activity_type, activity_label, location_label, weekday, time_range, duration])
    return (
        _table_html(
            [
                _quote_doc_text("planning_type_activity", language=language),
                _quote_doc_text("planning_activity", language=language),
                _quote_doc_text("planning_location", language=language),
                _quote_doc_text("planning_day", language=language),
                _quote_doc_text("planning_time", language=language),
                _quote_doc_text("planning_duration", language=language),
            ],
            rows,
            empty_label=_quote_doc_text("planning_empty", language=language),
        ),
        len(rows),
    )


def _planning_block_pdf_row(
    block: dict[str, Any],
    *,
    selected_solfege_slot: dict[str, Any] | None = None,
    language: str | None = None,
) -> list[str]:
    activity = _planning_activity_display_label(block, language=language)
    location = _localized_location_label(str(block.get("location_label") or "-").strip() or "-", language=language)
    day = _weekday_label_from_fields(block.get("weekday_label"), block.get("weekday"), language=language) or "-"
    start = str(block.get("start_time") or "").strip()
    end = str(block.get("end_time") or "").strip()
    time_range = f"{start} - {end}" if start and end else "-"
    duration = _duration_label(
        start_time=block.get("start_time"),
        end_time=block.get("end_time"),
        fallback_minutes=block.get("duration_minutes"),
    )
    try:
        weekday_value = int(block.get("weekday") or -99)
    except (TypeError, ValueError):
        weekday_value = -99
    selection_pending = bool(block.get("selection_pending")) or weekday_value == -1
    if not selection_pending:
        return [activity, location, day, time_range, duration]

    is_solfege_block = _is_solfege_planning_block(block)
    slot = _json_object(selected_solfege_slot)
    if is_solfege_block and slot:
        activity, _, _, _ = _pending_planning_block_display(block, language=language)
        slot_day = _weekday_label_from_fields(slot.get("weekday_label"), slot.get("weekday"), language=language)
        slot_start = str(slot.get("start_time") or slot.get("start") or "").strip()
        slot_end = str(slot.get("end_time") or slot.get("end") or "").strip()
        slot_time_range = f"{slot_start} - {slot_end}" if slot_start and slot_end else "-"
        slot_duration = _duration_label(
            start_time=slot_start,
            end_time=slot_end,
            fallback_minutes=slot.get("duration_minutes") or block.get("duration_minutes"),
        )
        slot_location = _localized_location_label(str(slot.get("location_label") or block.get("location_label") or "-").strip() or "-", language=language)
        if slot_day and slot_day != "-" and slot_time_range != "-":
            return [activity, slot_location, slot_day, slot_time_range, slot_duration]

    activity, day, time_range, duration = _pending_planning_block_display(block, language=language)
    return [activity, location, day, time_range, duration]


def _is_adjustment_line(line: QuoteLine) -> bool:
    line_type = (line.line_type or "").strip().lower()
    master_item_type = (line.master_item_type or "").strip().lower()
    return line_type in {"discount", "surcharge"} or master_item_type in {"discount_rule", "surcharge_rule"}


def _line_catalog_product_nature(line: QuoteLine) -> str:
    meta = line.meta if isinstance(line.meta, dict) else {}
    value = str(meta.get("catalog_product_nature") or meta.get("product_nature") or "").strip().lower()
    return value if value in {"material", "service"} else ""


def _service_product_ids_for_lines(*, db: Session | None, lines: list[QuoteLine]) -> set[UUID]:
    service_ids: set[UUID] = set()
    unresolved_ids: set[UUID] = set()
    for line in lines:
        if line.product_id is None:
            continue
        if _line_catalog_product_nature(line) == "service":
            service_ids.add(line.product_id)
            continue
        unresolved_ids.add(line.product_id)

    if db is not None and unresolved_ids:
        rows = db.execute(
            select(CatalogProduct.id).where(
                CatalogProduct.id.in_(list(unresolved_ids)),
                CatalogProduct.nature == "service",
            )
        ).all()
        service_ids.update(product_id for product_id, in rows if product_id is not None)
    return service_ids


def _line_is_service_fee(line: QuoteLine, *, service_product_ids: set[UUID] | None = None) -> bool:
    if _line_matches_pass_recup(line):
        return True
    if line.product_id is not None and service_product_ids and line.product_id in service_product_ids:
        return True
    category = (line.line_category or "").strip().lower()
    return category in {"other_fee", "fee", "immaterial_fee"}


def _line_groups(
    lines: list[QuoteLine],
    *,
    service_product_ids: set[UUID] | None = None,
) -> tuple[list[QuoteLine], list[QuoteLine], list[QuoteLine], list[QuoteLine], list[QuoteLine]]:
    services: list[QuoteLine] = []
    products: list[QuoteLine] = []
    kits: list[QuoteLine] = []
    adjustments: list[QuoteLine] = []
    other_fees: list[QuoteLine] = []
    for line in lines:
        if _is_adjustment_line(line):
            adjustments.append(line)
            continue
        if _line_is_service_fee(line, service_product_ids=service_product_ids):
            other_fees.append(line)
            continue
        if (line.line_category or "").strip().lower() == "service":
            services.append(line)
            continue
        if line.kit_id is not None or (line.master_item_type or "").strip().lower() == "kit":
            kits.append(line)
            continue
        products.append(line)
    return services, products, kits, adjustments, other_fees


def _small_description_html(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return (
        "<div style='font-size:10px;line-height:1.35;color:#64748b;margin-top:4px;'>"
        f"{escape(text).replace(chr(10), '<br/>')}"
        "</div>"
    )


def _unique_text_parts(*parts: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        raw = str(part or "").replace("\r\n", "\n").strip()
        if not raw:
            continue
        kept_lines: list[str] = []
        for line in raw.split("\n"):
            text = line.strip()
            if not text:
                continue
            normalized = " ".join(text.split()).casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            kept_lines.append(text)
        if kept_lines:
            result.extend(kept_lines)
    return result


def _product_long_descriptions_by_id(*, db: Session | None, products: list[QuoteLine]) -> dict[Any, str]:
    if db is None:
        return {}
    product_ids = [line.product_id for line in products if line.product_id is not None]
    if not product_ids:
        return {}
    rows = db.execute(
        select(CatalogProduct.id, CatalogProduct.long_description).where(CatalogProduct.id.in_(product_ids))
    ).all()
    result: dict[Any, str] = {}
    for product_id, long_description in rows:
        text = str(long_description or "").strip()
        if text:
            result[product_id] = text
    return result


def _kit_long_descriptions_by_id(*, db: Session | None, kits: list[QuoteLine]) -> dict[Any, str]:
    if db is None:
        return {}
    kit_ids = [line.kit_id for line in kits if line.kit_id is not None]
    if not kit_ids:
        return {}
    rows = db.execute(
        select(CatalogKit.id, CatalogKit.long_description).where(CatalogKit.id.in_(kit_ids))
    ).all()
    result: dict[Any, str] = {}
    for kit_id, long_description in rows:
        text = str(long_description or "").strip()
        if text:
            result[kit_id] = text
    return result


def _kit_composition_by_id(*, db: Session | None, kits: list[QuoteLine], language: str | None = None) -> dict[Any, list[str]]:
    if db is None:
        return {}
    kit_ids = [line.kit_id for line in kits if line.kit_id is not None]
    if not kit_ids:
        return {}
    rows = db.execute(
        select(CatalogKitItem.kit_id, CatalogKitItem.quantity, CatalogProduct.title)
        .select_from(CatalogKitItem)
        .outerjoin(CatalogProduct, CatalogProduct.id == CatalogKitItem.product_id)
        .where(CatalogKitItem.kit_id.in_(kit_ids))
        .order_by(CatalogKitItem.kit_id.asc(), CatalogKitItem.display_order.asc(), CatalogKitItem.created_at.asc())
    ).all()
    result: dict[Any, list[str]] = {}
    for kit_id, quantity, product_title in rows:
        fallback_label = _quote_doc_text("table_material", language=language)
        label = str(product_title or fallback_label).strip() or fallback_label
        quantity_value = _decimal_from_any(quantity, Decimal("1"))
        quantity_label = _compact_quantity_label(quantity)
        rendered_label = f"{label} x {quantity_label}" if quantity_value > Decimal("1") else label
        rendered_label = _localized_catalog_text(rendered_label, language=language)
        result.setdefault(kit_id, []).append(rendered_label)
    return result


def _kit_composition_html(items: list[str], *, language: str | None = None) -> str:
    if not items:
        return ""
    rendered_items = "<br/>".join(escape(item) for item in items)
    return (
        "<div style='font-size:10px;line-height:1.35;color:#475467;margin-top:4px;'>"
        f"<strong>{escape(_quote_doc_text('kit_includes', language=language))} :</strong><br/>"
        f"{rendered_items}"
        "</div>"
    )


def _load_quote_template_snapshot(*, db: Session | None, quote: Quote) -> tuple[str, str]:
    if db is not None and quote.quote_template_version_id is not None:
        version = db.scalar(select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == quote.quote_template_version_id))
        if version is not None:
            snapshot = version.content_snapshot or {}
            subject = str(snapshot.get("subject_template") or "").strip()
            body = str(snapshot.get("body_template") or "").strip()
            if subject or body:
                return subject, body
    meta = quote.meta or {}
    subject = str(meta.get("template_subject") or "").strip()
    body = str(meta.get("template_body") or "").strip()
    return subject, body


def _quote_template_disables_pass_recup(*, db: Session | None, quote: Quote) -> bool:
    candidates: list[str] = []
    target = ""
    if db is not None:
        template: QuoteTemplate | None = None
        if quote.quote_template_id is not None:
            template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == quote.quote_template_id))
        elif quote.quote_template_version_id is not None:
            version = db.scalar(select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == quote.quote_template_version_id))
            if version is not None:
                template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == version.quote_template_id))
        if template is not None:
            target = str(template.target or "").strip().lower()
            candidates.extend(
                [
                    str(template.name or "").strip().lower(),
                    str(template.code or "").strip().lower(),
                ]
            )
    meta = _json_object(quote.meta)
    candidates.extend(
        [
            str(meta.get("quote_template_name") or "").strip().lower(),
            str(meta.get("quote_template_code") or "").strip().lower(),
            str(meta.get("template_name") or "").strip().lower(),
        ]
    )
    if target in {"eveil", "initiation"}:
        return True
    searchable = " ".join(_searchable_text(item) for item in candidates if item)
    compact = re.sub(r"[^a-z0-9]+", "", searchable)
    words = set(re.split(r"[^a-z0-9]+", searchable))
    if "barleduc" in compact or "bld" in words:
        return True
    return any(("eveil" in item) or ("initiation" in item) for item in candidates if item)


def _quote_template_allows_end_year_concert(*, db: Session | None, quote: Quote) -> bool:
    meta = _json_object(quote.meta)
    mode = str(meta.get("end_year_concert_option_mode") or meta.get("concert_option_mode") or "").strip().lower()
    if mode in {"enabled", "required", "optional"}:
        return True
    if mode in {"disabled", "off", "none"}:
        return False

    candidates: list[str] = [
        str(meta.get("quote_template_name") or "").strip().lower(),
        str(meta.get("quote_template_code") or "").strip().lower(),
        str(meta.get("template_name") or "").strip().lower(),
    ]
    if db is not None:
        template: QuoteTemplate | None = None
        if quote.quote_template_id is not None:
            template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == quote.quote_template_id))
        elif quote.quote_template_version_id is not None:
            version = db.scalar(select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == quote.quote_template_version_id))
            if version is not None:
                template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == version.quote_template_id))
        if template is not None:
            candidates.extend(
                [
                    str(template.name or "").strip().lower(),
                    str(template.code or "").strip().lower(),
                    str(template.description or "").strip().lower(),
                ]
            )

    searchable = " ".join(_searchable_text(item) for item in candidates if item)
    return "concert" in searchable and "option" in searchable


def _load_terms_template_content(*, db: Session | None, quote: Quote) -> tuple[str, str]:
    if db is not None and quote.terms_template_version_id is not None:
        version = db.scalar(select(TermsTemplateVersion).where(TermsTemplateVersion.id == quote.terms_template_version_id))
        if version is not None:
            snapshot = version.content_snapshot or {}
            label = str(snapshot.get("version_label") or "").strip()
            content = str(snapshot.get("content") or "").strip()
            if label or content:
                return label, content
    cgv_snapshot = quote.cgv_snapshot or {}
    return str(cgv_snapshot.get("version_label") or "").strip(), str(cgv_snapshot.get("content") or "").strip()


def _user_address(user: User | None) -> str:
    if user is None:
        return ""
    return " ".join(
        part
        for part in [user.address_line or "", user.postal_code or "", user.city or ""]
        if str(part or "").strip()
    ).strip()


def _is_child_user(user: User | None) -> bool:
    if user is None:
        return False
    kind = getattr(user.client_kind, "value", user.client_kind)
    return str(kind or "").strip().upper() == ClientKind.CHILD.value


def _family_adult_for_child(db: Session, child_id: UUID) -> User | None:
    rows = db.execute(
        select(ClientFamilyLink, User)
        .join(User, User.id == ClientFamilyLink.adult_user_id)
        .where(ClientFamilyLink.child_user_id == child_id)
        .order_by(ClientFamilyLink.is_billing_recipient.desc(), ClientFamilyLink.created_at.asc())
    ).all()
    if not rows:
        return None
    _, adult = rows[0]
    return adult


def _resolved_parent_address_for_quote_adult(*, db: Session, quote: Quote, adult: User | None) -> str:
    typeform_parts = _typeform_parent_address_parts_from_quote(db=db, quote=quote)
    if adult is None:
        return _format_address_parts(
            address_line=typeform_parts["address_line"],
            address_line_2=typeform_parts["address_line_2"],
            postal_code=typeform_parts["postal_code"],
            city=typeform_parts["city"],
            country=typeform_parts["country"],
        )
    address_line = typeform_parts["address_line"] or str(adult.address_line or "").strip()
    postal_code = typeform_parts["postal_code"] or str(adult.postal_code or "").strip()
    city = typeform_parts["city"] or str(adult.city or "").strip()
    country = str(typeform_parts["country"] or "").strip()
    return _format_address_parts(address_line=address_line, postal_code=postal_code, city=city, country=country)


def _apply_child_client_family_data(*, db: Session | None, quote: Quote, values: dict[str, str]) -> dict[str, str]:
    if db is None or quote.client_id is None:
        return values
    normalized_payload = _json_object(_json_object(_json_object(quote.meta).get("typeform_intake")).get("normalized_payload"))
    if not values.get("child_birth_date"):
        values["child_birth_date"] = str(normalized_payload.get("child_birth_date") or "").strip()
    child = db.scalar(select(User).where(User.id == quote.client_id))
    if child is None or not _is_child_user(child):
        return values

    values["prospect_type"] = "child"
    values["prospect_type_label"] = "Enfant"
    values["child_first_name"] = values.get("child_first_name") or (child.first_name or "").strip()
    values["child_last_name"] = values.get("child_last_name") or (child.last_name or "").strip()
    values["child_full_name"] = values.get("child_full_name") or _name(child.first_name, child.last_name, fallback="")
    if not values.get("child_birth_date") and child.birth_date is not None:
        values["child_birth_date"] = child.birth_date.isoformat()

    adult = _family_adult_for_child(db, child.id)
    if adult is not None:
        values["parent_first_name"] = (adult.first_name or "").strip() or values.get("parent_first_name") or ""
        values["parent_last_name"] = (adult.last_name or "").strip() or values.get("parent_last_name") or ""
        values["parent_full_name"] = _name(adult.first_name, adult.last_name, fallback="") or values.get("parent_full_name") or ""
        values["parent_email"] = _public_email(adult.email) or values.get("parent_email") or ""
        values["parent_phone"] = (adult.mobile_phone_1 or adult.phone or "").strip() or values.get("parent_phone") or ""
        values["parent_address"] = values.get("parent_address") or _resolved_parent_address_for_quote_adult(
            db=db,
            quote=quote,
            adult=adult,
        )
    return values


def _apply_typeform_contact_data(*, db: Session | None, quote: Quote, values: dict[str, str]) -> dict[str, str]:
    quote_meta = _json_object(quote.meta)
    normalized_payload = _json_object(_json_object(quote_meta.get("typeform_intake")).get("normalized_payload"))
    if not normalized_payload:
        return values

    typeform_address = _typeform_parent_address_from_quote(db=db, quote=quote).strip()
    typeform_phone = _typeform_contact_phone_from_quote(db=db, quote=quote).strip()
    customer_type = str(normalized_payload.get("customer_type") or "").strip().lower()
    has_child_fields = any(
        str(normalized_payload.get(key) or "").strip()
        for key in ("child_first_name", "child_last_name", "child_birth_date")
    )
    prospect_type = "child" if customer_type == "child" or has_child_fields else "adult"
    values["prospect_type"] = prospect_type
    values["prospect_type_label"] = "Enfant" if prospect_type == "child" else "Adulte"

    parent_first_name = str(
        normalized_payload.get("parent_first_name") or normalized_payload.get("adult_first_name") or ""
    ).strip()
    parent_last_name = str(
        normalized_payload.get("parent_last_name") or normalized_payload.get("adult_last_name") or ""
    ).strip()
    parent_email = _public_email(str(normalized_payload.get("parent_email") or normalized_payload.get("adult_email") or ""))
    if prospect_type == "child":
        child_first_name = str(normalized_payload.get("child_first_name") or "").strip()
        child_last_name = str(normalized_payload.get("child_last_name") or "").strip()
        values["child_first_name"] = values.get("child_first_name") or child_first_name
        values["child_last_name"] = values.get("child_last_name") or child_last_name
        values["child_full_name"] = values.get("child_full_name") or _name(child_first_name, child_last_name, fallback="")
        values["child_birth_date"] = values.get("child_birth_date") or str(normalized_payload.get("child_birth_date") or "").strip()
        values["parent_first_name"] = values.get("parent_first_name") or parent_first_name
        values["parent_last_name"] = values.get("parent_last_name") or parent_last_name
        values["parent_full_name"] = values.get("parent_full_name") or _name(parent_first_name, parent_last_name, fallback="")
        values["parent_email"] = values.get("parent_email") or parent_email
        values["parent_phone"] = values.get("parent_phone") or typeform_phone
        values["parent_address"] = values.get("parent_address") or typeform_address
    else:
        values["adult_first_name"] = values.get("adult_first_name") or parent_first_name
        values["adult_last_name"] = values.get("adult_last_name") or parent_last_name
        values["adult_full_name"] = values.get("adult_full_name") or _name(parent_first_name, parent_last_name, fallback="")
        values["adult_email"] = values.get("adult_email") or parent_email
        values["adult_phone"] = values.get("adult_phone") or typeform_phone
        values["adult_address"] = values.get("adult_address") or typeform_address
    return values


def _resolve_prospect_data(*, db: Session | None, quote: Quote) -> dict[str, str]:
    values: dict[str, str] = {
        "prospect_type": "adult",
        "prospect_type_label": "Adulte",
        "adult_first_name": "",
        "adult_last_name": "",
        "adult_full_name": "",
        "adult_email": "",
        "adult_phone": "",
        "adult_address": "",
        "parent_first_name": "",
        "parent_last_name": "",
        "parent_full_name": "",
        "parent_email": "",
        "parent_phone": "",
        "parent_address": "",
        "child_first_name": "",
        "child_last_name": "",
        "child_full_name": "",
        "child_birth_date": "",
    }
    if db is None or quote.prospect_id is None:
        values = _apply_typeform_contact_data(db=db, quote=quote, values=values)
        return _apply_child_client_family_data(db=db, quote=quote, values=values)

    prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id))
    if prospect is None:
        return _apply_child_client_family_data(db=db, quote=quote, values=values)

    meta = prospect.meta or {}
    typeform_parent_address = _typeform_parent_address_from_quote(db=db, quote=quote).strip()
    typeform_contact_phone = _typeform_contact_phone_from_quote(db=db, quote=quote).strip()
    prospect_type = "child" if str(meta.get("prospect_type") or "").strip().lower() == "child" else "adult"
    values["prospect_type"] = prospect_type
    values["prospect_type_label"] = "Enfant" if prospect_type == "child" else "Adulte"

    if prospect_type == "child":
        child_meta = meta.get("child") if isinstance(meta.get("child"), dict) else {}
        parent_meta = meta.get("parent_referent") if isinstance(meta.get("parent_referent"), dict) else {}
        child_first_name = str((child_meta or {}).get("first_name") or prospect.first_name or "").strip()
        child_last_name = str((child_meta or {}).get("last_name") or prospect.last_name or "").strip()
        values["child_first_name"] = child_first_name
        values["child_last_name"] = child_last_name
        values["child_full_name"] = _name(child_first_name, child_last_name, fallback="")
        values["child_birth_date"] = str((child_meta or {}).get("birth_date") or "").strip()

        parent_first_name = str((parent_meta or {}).get("first_name") or "").strip()
        parent_last_name = str((parent_meta or {}).get("last_name") or "").strip()
        parent_email = _public_email(str((parent_meta or {}).get("email") or prospect.email or ""))
        parent_phone = str((parent_meta or {}).get("phone") or prospect.phone or typeform_contact_phone or "").strip()
        parent_address = str((parent_meta or {}).get("address") or "").strip()
        if prospect.parent_prospect_id is not None:
            parent = db.scalar(select(Prospect).where(Prospect.id == prospect.parent_prospect_id))
            if parent is not None:
                parent_first_name = parent.first_name or parent_first_name
                parent_last_name = parent.last_name or parent_last_name
                parent_email = _public_email(parent.email) or parent_email
                parent_phone = (parent.phone or parent_phone).strip()
                if not parent_address:
                    parent_meta_data = parent.meta or {}
                    parent_address = str(parent_meta_data.get("adult_address") or "").strip()
        if not parent_address:
            parent_address = typeform_parent_address

        values["parent_first_name"] = parent_first_name
        values["parent_last_name"] = parent_last_name
        values["parent_full_name"] = _name(parent_first_name, parent_last_name, fallback="")
        values["parent_email"] = parent_email
        values["parent_phone"] = parent_phone
        values["parent_address"] = parent_address
    else:
        values["adult_first_name"] = (prospect.first_name or "").strip()
        values["adult_last_name"] = (prospect.last_name or "").strip()
        values["adult_full_name"] = _name(prospect.first_name, prospect.last_name, fallback="")
        values["adult_email"] = _public_email(prospect.email)
        values["adult_phone"] = (prospect.phone or typeform_contact_phone or "").strip()
        values["adult_address"] = str(meta.get("adult_address") or typeform_parent_address or "").strip()

    return _apply_child_client_family_data(db=db, quote=quote, values=values)


def _resolve_client_data(*, db: Session | None, quote: Quote) -> dict[str, str]:
    values: dict[str, str] = {
        "client_first_name": "",
        "client_last_name": "",
        "client_full_name": "",
        "client_email": "",
        "client_phone": "",
        "client_address": "",
    }
    if db is None or quote.client_id is None:
        return values
    user = db.scalar(select(User).where(User.id == quote.client_id))
    if user is None:
        return values
    values["client_first_name"] = (user.first_name or "").strip()
    values["client_last_name"] = (user.last_name or "").strip()
    values["client_full_name"] = _name(user.first_name, user.last_name, fallback="")
    values["client_email"] = _public_email(user.email)
    values["client_phone"] = (user.mobile_phone_1 or user.phone or "").strip()
    values["client_address"] = _user_address(user)
    return values


def _resolve_schedule_visibility_by_audience(*, quote: Quote) -> dict[str, bool]:
    default_visibility = {
        AUDIENCE_ADMIN_PREVIEW: True,
        AUDIENCE_PUBLIC_PAGE: False,
        AUDIENCE_CLIENT_PDF: False,
    }
    payment_snapshot = _json_object(quote.payment_terms_snapshot)
    snapshot_visibility = _json_object(payment_snapshot.get("schedule_visibility"))
    if snapshot_visibility:
        return {
            AUDIENCE_ADMIN_PREVIEW: _is_true(
                snapshot_visibility.get(AUDIENCE_ADMIN_PREVIEW, default_visibility[AUDIENCE_ADMIN_PREVIEW])
            ),
            AUDIENCE_PUBLIC_PAGE: _is_true(
                snapshot_visibility.get(AUDIENCE_PUBLIC_PAGE, default_visibility[AUDIENCE_PUBLIC_PAGE])
            ),
            AUDIENCE_CLIENT_PDF: _is_true(
                snapshot_visibility.get(AUDIENCE_CLIENT_PDF, default_visibility[AUDIENCE_CLIENT_PDF])
            ),
        }
    meta = _json_object(quote.meta)
    visibility_root = _json_object(meta.get("document_visibility"))
    raw = _json_object(visibility_root.get("payment_schedule_detailed"))
    if not raw:
        raw = _json_object(meta.get("payment_schedule_visibility"))
    if not raw:
        return default_visibility
    return {
        AUDIENCE_ADMIN_PREVIEW: _is_true(raw.get(AUDIENCE_ADMIN_PREVIEW, default_visibility[AUDIENCE_ADMIN_PREVIEW])),
        AUDIENCE_PUBLIC_PAGE: _is_true(raw.get(AUDIENCE_PUBLIC_PAGE, default_visibility[AUDIENCE_PUBLIC_PAGE])),
        AUDIENCE_CLIENT_PDF: _is_true(raw.get(AUDIENCE_CLIENT_PDF, default_visibility[AUDIENCE_CLIENT_PDF])),
    }


def _resolve_payment_method_label(*, quote: Quote) -> str:
    language = _quote_doc_language(quote=quote)
    snapshot = _json_object(quote.payment_terms_snapshot)
    for key in ("plan_name", "payment_plan_name", "payment_method_label", "payment_method"):
        value = str(snapshot.get(key) or "").strip()
        if value:
            return value
    meta = _json_object(quote.meta)
    for key in ("payment_plan_label", "payment_plan_name", "payment_method_label", "payment_method"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return _quote_doc_text("payment_method_unspecified", language=language)


def _line_matches_pass_recup(line: QuoteLine) -> bool:
    tokens = [
        str(line.title or ""),
        str(line.code or ""),
        str(line.line_type or ""),
        str(line.line_category or ""),
        str(line.master_item_type or ""),
    ]
    haystack = " ".join(tokens).strip().lower()
    return "pass recup" in haystack or "pass_recup" in haystack or "passrecup" in haystack


def _line_matches_masterclass(line: QuoteLine) -> bool:
    tokens = [
        str(line.title or ""),
        str(line.code or ""),
        str(line.line_type or ""),
        str(line.line_category or ""),
        str(line.master_item_type or ""),
    ]
    haystack = " ".join(tokens).strip().lower()
    return "masterclass" in haystack or "master class" in haystack


def _line_matches_end_year_concert(line: QuoteLine) -> bool:
    tokens = [
        str(line.title or ""),
        str(line.code or ""),
        str(line.line_type or ""),
        str(line.line_category or ""),
        str(line.master_item_type or ""),
    ]
    haystack = _searchable_text(" ".join(tokens))
    return "concert" in haystack


def _masterclass_blocks_from_calendar_snapshot(snapshot: dict[str, Any], *, language: str | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in _json_list(snapshot.get("blocks")):
        if not isinstance(raw, dict):
            continue
        activity_label = str(raw.get("activity_label") or "").strip()
        activity_code = str(raw.get("activity_code") or raw.get("activity_service_code") or "").strip()
        haystack = f"{activity_label} {activity_code}".strip().lower()
        if "masterclass" not in haystack and "master class" not in haystack:
            continue
        location_label = str(raw.get("location_label") or "").strip()
        selection_pending = bool(raw.get("selection_pending"))
        weekday_label = str(raw.get("weekday_label") or "").strip() or _weekday_label(raw.get("weekday"), language=language)
        start_time = str(raw.get("start_time") or "").strip()
        end_time = str(raw.get("end_time") or "").strip()
        session_label = str(raw.get("session_label") or "").strip()
        if not session_label:
            if selection_pending:
                session_label = _quote_doc_text("to_select", language=language)
            elif weekday_label and start_time and end_time:
                session_label = f"{weekday_label} {start_time}-{end_time}"
            elif weekday_label:
                session_label = weekday_label
        rows.append(
            {
                "session": session_label,
                "location_label": location_label,
                "activity_label": activity_label or "Masterclass",
            }
        )
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in rows:
        key = (
            str(item.get("session") or "").strip().lower(),
            str(item.get("location_label") or "").strip().lower(),
            str(item.get("activity_label") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _extract_solfege_level_from_text(value: Any) -> str:
    raw = str(value or "").strip()
    match = re.search(r"niveau\s*([1-5])", raw, flags=re.IGNORECASE)
    if match and match.group(1):
        return match.group(1)
    return ""


def _solfege_pending_block_info(snapshot: dict[str, Any], *, db: Session | None = None, language: str | None = None) -> dict[str, Any]:
    has_pending_selection = False
    level_code = ""
    slot_labels: list[str] = []

    for raw in _json_list(snapshot.get("blocks")):
        if not isinstance(raw, dict):
            continue
        activity_label = str(raw.get("activity_label") or "").strip()
        activity_code = str(raw.get("activity_code") or raw.get("activity_service_code") or "").strip()
        haystack = _searchable_text(f"{activity_label} {activity_code}")
        if "solfege" not in haystack:
            continue
        try:
            weekday_value = int(raw.get("weekday") or -99)
        except (TypeError, ValueError):
            weekday_value = -99
        selection_pending = bool(raw.get("selection_pending")) or weekday_value == -1
        if selection_pending:
            has_pending_selection = True
        if not level_code:
            level_code = str(raw.get("pending_solfege_level") or "").strip() or _extract_solfege_level_from_text(activity_label)
        slot_count_before = len(slot_labels)
        for raw_slot in _json_list(raw.get("pending_slot_options")):
            if not isinstance(raw_slot, dict):
                continue
            label = _slot_label(raw_slot, fallback_location_label=str(raw.get("location_label") or "").strip(), language=language)
            if label:
                slot_labels.append(label)
                continue
            weekday_text = str(raw_slot.get("weekday_label") or "").strip() or _weekday_label(raw_slot.get("weekday"), language=language)
            start = str(raw_slot.get("start_time") or raw_slot.get("start") or "").strip()
            end = str(raw_slot.get("end_time") or raw_slot.get("end") or "").strip()
            if weekday_text and start and end:
                slot_labels.append(f"{weekday_text} {start}-{end}")
        if selection_pending and len(slot_labels) == slot_count_before:
            slot_labels.extend(
                _solfege_slot_labels_from_rule(
                    _matching_solfege_rule_for_pending_block(
                        db,
                        level_code=level_code,
                        location_id=raw.get("location_id"),
                        modality=raw.get("modality"),
                    ),
                    location_label=str(raw.get("location_label") or "").strip(),
                    language=language,
                )
            )

    for raw_recommendation in _json_list(snapshot.get("typeform_recommendations")):
        recommendation = _json_object(raw_recommendation)
        if str(recommendation.get("selected_session_id") or "").strip():
            continue
        activity_name = str(recommendation.get("activity_name") or "").strip()
        if "solfege" not in _searchable_text(activity_name):
            continue
        has_pending_selection = True
        if not level_code:
            level_code = _extract_solfege_level_from_text(activity_name)
        for raw_option in _json_list(recommendation.get("options")):
            option = _json_object(raw_option)
            weekday_text = str(option.get("weekday_label") or "").strip()
            start = str(option.get("start_time_label") or "").strip()
            location = str(option.get("location_name") or "").strip()
            label = " · ".join(
                part
                for part in (" ".join(part for part in (weekday_text, start) if part), location)
                if part
            )
            if label:
                slot_labels.append(_sanitize_slot_label_text(label, language=language))

    return {
        "has_pending_selection": has_pending_selection,
        "level_code": level_code,
        "slot_labels": _unique_text_parts(*slot_labels),
    }


def _line_matches_solfege_activity(line: QuoteLine | Any) -> bool:
    meta = _json_object(getattr(line, "meta", None))
    haystack = _searchable_text(
        " ".join(
            str(part or "")
            for part in (
                getattr(line, "title", None),
                getattr(line, "description", None),
                getattr(line, "code", None),
                meta.get("activity_name"),
                meta.get("typeform_automatic_line"),
                meta.get("source"),
            )
        )
    )
    return "solfege" in haystack and getattr(line, "activity_id", None) is not None


def _solfege_level_from_line(line: QuoteLine | Any) -> str:
    meta = _json_object(getattr(line, "meta", None))
    for value in (
        getattr(line, "title", None),
        getattr(line, "description", None),
        getattr(line, "code", None),
        meta.get("activity_name"),
    ):
        level = _extract_solfege_level_from_text(value)
        if level:
            return level
    return ""


def _solfege_level_from_block(block: dict[str, Any]) -> str:
    return (
        str(block.get("pending_solfege_level") or "").strip()
        or _extract_solfege_level_from_text(block.get("activity_label"))
        or _extract_solfege_level_from_text(block.get("activity_name"))
    )


def _solfege_block_is_pending(block: dict[str, Any]) -> bool:
    try:
        weekday = int(block.get("weekday"))
    except (TypeError, ValueError):
        weekday = -1
    return bool(block.get("selection_pending")) or weekday < 0


def _solfege_activity_ids_are_compatible(
    *,
    line_activity_id: str,
    block_activity_id: str,
    line_level: str,
    block_level: str,
) -> bool:
    if not line_activity_id or not block_activity_id or block_activity_id == line_activity_id:
        return True
    return bool(line_level and block_level and line_level == block_level)


def _slot_from_solfege_block(block: dict[str, Any], *, level_code: str = "", language: str | None = None) -> dict[str, Any]:
    slot = {
        "weekday": block.get("weekday"),
        "weekday_label": str(block.get("weekday_label") or "").strip() or _weekday_label(block.get("weekday"), language=language),
        "start_time": str(block.get("start_time") or block.get("start") or "").strip(),
        "end_time": str(block.get("end_time") or block.get("end") or "").strip(),
        "duration_minutes": block.get("duration_minutes"),
        "location_id": block.get("location_id"),
        "location_label": str(block.get("location_label") or "").strip(),
        "modality": block.get("modality"),
        "level_code": level_code or _solfege_level_from_block(block),
    }
    slot = {key: value for key, value in slot.items() if value not in ("", None)}
    label = _slot_label(slot, language=language)
    if label and label != "-":
        slot["label"] = label
    return slot


def _current_solfege_document_info(
    *,
    lines: list[QuoteLine],
    calendar_snapshot: dict[str, Any],
    quote_selected_slot: dict[str, Any] | None = None,
    quote_level: Any = None,
    quote_duration_minutes: Any = None,
    language: str | None = None,
) -> dict[str, Any]:
    solfege_lines = [line for line in lines if _line_matches_solfege_activity(line)]
    current_line = solfege_lines[0] if solfege_lines else None
    line_activity_id = str(getattr(current_line, "activity_id", "") or "").strip() if current_line is not None else ""
    line_level = _solfege_level_from_line(current_line) if current_line is not None else ""

    matching_blocks: list[dict[str, Any]] = []
    for raw_block in _json_list(calendar_snapshot.get("blocks")):
        if not isinstance(raw_block, dict):
            continue
        block = dict(raw_block)
        if not _is_solfege_planning_block(block):
            continue
        block_activity_id = str(block.get("activity_id") or "").strip()
        block_level = _solfege_level_from_block(block)
        if not _solfege_activity_ids_are_compatible(
            line_activity_id=line_activity_id,
            block_activity_id=block_activity_id,
            line_level=line_level,
            block_level=block_level,
        ):
            continue
        if line_level and block_level and block_level != line_level:
            continue
        matching_blocks.append(block)

    def _block_score(block: dict[str, Any]) -> tuple[int, int, int, str]:
        block_activity_id = str(block.get("activity_id") or "").strip()
        block_level = _solfege_level_from_block(block)
        return (
            0 if not _solfege_block_is_pending(block) else 1,
            0 if line_activity_id and block_activity_id == line_activity_id else 1,
            0 if line_level and block_level == line_level else 1,
            str(block.get("start_time") or ""),
        )

    active_block = min(matching_blocks, key=_block_score) if matching_blocks else None
    block_level = _solfege_level_from_block(active_block) if active_block is not None else ""
    has_current_source = bool(current_line or active_block)
    selected_slot = _json_object(quote_selected_slot) if has_current_source else {}
    slot_level = str(selected_slot.get("level_code") or "").strip()
    if line_level and slot_level and slot_level != line_level:
        selected_slot = {}
    if active_block is not None and not _solfege_block_is_pending(active_block):
        selected_slot = _slot_from_solfege_block(active_block, level_code=line_level or block_level, language=language)

    duration_minutes = None
    if current_line is not None:
        duration_minutes = getattr(current_line, "duration_minutes", None)
    if not duration_minutes and active_block is not None:
        duration_minutes = active_block.get("duration_minutes")
    if not duration_minutes:
        duration_minutes = selected_slot.get("duration_minutes")
    if not duration_minutes and has_current_source:
        duration_minutes = quote_duration_minutes

    return {
        "has_current_solfege": has_current_source,
        "level_code": line_level
        or block_level
        or (str(selected_slot.get("level_code") or quote_level or "").strip() if has_current_source else ""),
        "duration_minutes": duration_minutes,
        "selected_slot": selected_slot,
    }


def _calendar_snapshot_with_current_solfege_block(
    calendar_snapshot: dict[str, Any],
    *,
    db: Session | None = None,
    quote: Quote | None = None,
    lines: list[QuoteLine],
    selected_solfege_slot: dict[str, Any] | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    snapshot = dict(_json_object(calendar_snapshot))
    blocks = [dict(item) for item in _json_list(snapshot.get("blocks")) if isinstance(item, dict)]
    solfege_lines = [line for line in lines if _line_matches_solfege_activity(line)]
    if not solfege_lines:
        snapshot["blocks"] = blocks
        return snapshot

    line = solfege_lines[0]
    line_activity_id = str(getattr(line, "activity_id", "") or "").strip()
    line_level = _solfege_level_from_line(line)
    slot = _json_object(selected_solfege_slot)
    slot_level = str(slot.get("level_code") or "").strip()
    if line_level and slot_level and slot_level != line_level:
        slot = {}

    def _matches_current_solfege(block: dict[str, Any]) -> bool:
        if not _is_solfege_planning_block(block):
            return False
        block_activity_id = str(block.get("activity_id") or "").strip()
        block_level = _solfege_level_from_block(block)
        if not _solfege_activity_ids_are_compatible(
            line_activity_id=line_activity_id,
            block_activity_id=block_activity_id,
            line_level=line_level,
            block_level=block_level,
        ):
            return False
        if line_level and block_level and block_level != line_level:
            return False
        return True

    matching_indices = [index for index, block in enumerate(blocks) if _matches_current_solfege(block)]
    if not slot:
        snapshot["blocks"] = blocks
        return snapshot

    base_block = blocks[matching_indices[0]] if matching_indices else {}
    start_time = str(slot.get("start_time") or base_block.get("start_time") or "").strip()
    end_time = str(slot.get("end_time") or base_block.get("end_time") or "").strip()
    weekday = slot.get("weekday", base_block.get("weekday"))
    if not start_time or not end_time or weekday in ("", None):
        snapshot["blocks"] = blocks
        return snapshot

    duration_minutes = (
        slot.get("duration_minutes")
        or getattr(line, "duration_minutes", None)
        or base_block.get("duration_minutes")
    )
    location_label = str(slot.get("location_label") or base_block.get("location_label") or "").strip()
    modality = slot.get("modality") or base_block.get("modality")
    if not modality and location_label.lower() in {"online", "en ligne"}:
        modality = "ONLINE"

    activity_label = str(getattr(line, "title", "") or base_block.get("activity_label") or "").strip()
    if not activity_label:
        level_suffix = f" - Niveau {line_level}" if line_level else ""
        activity_label = f"{_quote_doc_text('course_solfege', language=language)}{level_suffix}"

    recommendation_key = str(base_block.get("recommendation_key") or "").strip()
    if not recommendation_key:
        line_meta = _json_object(getattr(line, "meta", None))
        source_key = str(line_meta.get("typeform_automatic_line") or "").strip()
        recommendation_key = f"{line_activity_id}:{source_key}" if source_key else line_activity_id

    live_rows: list[tuple[CourseSession, CourseType, Location]] = []
    live_location: Location | None = None
    parsed_activity_id = _parse_uuid(line_activity_id)
    if parsed_activity_id is not None and quote is not None:
        live_rows, live_location = _selected_solfege_live_series_for_slot(
            db,
            activity_id=parsed_activity_id,
            selected_slot=slot,
            school_year_label=getattr(quote, "school_year_label", None),
        )
    live_dates: list[date] = []
    for session_obj, _activity, location in live_rows:
        zone = _safe_zoneinfo(session_obj.timezone or location.timezone)
        live_dates.append(session_obj.start_at_utc.astimezone(zone).date())
    if live_rows and live_location is not None:
        location_label = live_location.name
        modality = _course_type_modality(live_rows[0][1], live_location)

    normalized_block = dict(base_block)
    normalized_block.update(
        {
            "activity_id": line_activity_id or base_block.get("activity_id"),
            "activity_label": activity_label,
            "location_id": str(live_location.id) if live_location is not None else slot.get("location_id") or base_block.get("location_id"),
            "location_label": location_label or "-",
            "recommendation_key": recommendation_key or None,
            "series_key": str(live_rows[0][0].recurrence_group_id or live_rows[0][0].id) if live_rows else None,
            "weekday": weekday,
            "weekday_label": str(slot.get("weekday_label") or "").strip()
            or _weekday_label(weekday, language=language),
            "start_time": start_time,
            "end_time": end_time,
            "duration_minutes": duration_minutes,
            "modality": modality,
            "start_date": min(live_dates).isoformat() if live_dates else None,
            "end_date": max(live_dates).isoformat() if live_dates else None,
            "sessions_count": len(live_rows) if live_rows else None,
            "selection_pending": not bool(live_rows),
            "pending_solfege_level": line_level or base_block.get("pending_solfege_level") or slot.get("level_code"),
            "pending_slot_options": [] if live_rows else base_block.get("pending_slot_options") or [],
            "source": "selected_solfege_slot",
        }
    )
    normalized_block = {key: value for key, value in normalized_block.items() if value not in ("", None)}

    if matching_indices:
        blocks[matching_indices[0]] = normalized_block
    else:
        blocks.append(normalized_block)
    snapshot["blocks"] = blocks
    sessions: list[dict[str, Any]] = []
    for raw_session in _json_list(snapshot.get("sessions")):
        if not isinstance(raw_session, dict):
            continue
        if line_activity_id and str(raw_session.get("activity_id") or "").strip() == line_activity_id:
            continue
        sessions.append(dict(raw_session))
    for session_obj, activity, location in live_rows:
        sessions.append(
            _session_snapshot_from_live_row(
                session_obj,
                activity,
                location,
                recommendation_key=recommendation_key,
            )
        )
    sessions, _ = _dedupe_calendar_sessions(sessions)
    sessions.sort(
        key=lambda item: (
            str(item.get("date") or ""),
            str(item.get("start_time") or ""),
            str(item.get("activity_label") or ""),
        )
    )
    snapshot["sessions"] = sessions
    snapshot["sessions_count"] = len(sessions)
    snapshot_solfege = _json_object(snapshot.get("solfege"))
    snapshot_solfege["selected_slot"] = slot
    snapshot["solfege"] = snapshot_solfege
    return snapshot


def _resolve_pass_recup_enabled(*, meta: dict[str, Any], lines: list[QuoteLine]) -> bool:
    mode = str(meta.get("pass_recup_mode") or "").strip().lower()
    if mode == "enabled":
        return True
    if mode == "disabled":
        return False
    if _is_true(meta.get("pass_recup_enabled")):
        return True
    return any(_line_matches_pass_recup(line) for line in lines)


def _extract_document_context(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str,
) -> dict[str, Any]:
    language = _quote_doc_language(quote=quote)
    prospect_data = _resolve_prospect_data(db=db, quote=quote)
    prospect_data["prospect_type_label"] = _quote_doc_text(
        "prospect_type_child" if str(prospect_data.get("prospect_type") or "").lower() == "child" else "prospect_type_adult",
        language=language,
    )
    client_data = _resolve_client_data(db=db, quote=quote)

    payment_snapshot = _json_object(quote.payment_terms_snapshot)
    schedule = [item for item in _json_list(payment_snapshot.get("schedule")) if isinstance(item, dict)]
    schedule = _normalise_check_schedule_deposit_months(schedule, language=language)
    has_installment_schedule = len(schedule) > 1
    schedule_visibility = _resolve_schedule_visibility_by_audience(quote=quote)
    deposit_data = _json_object(payment_snapshot.get("deposit"))
    meta = _json_object(quote.meta)
    if not deposit_data:
        deposit_data = _json_object(meta.get("pre_registration_deposit"))
    deposit_enabled = _is_true(deposit_data.get("enabled"))
    deposit_amount_ttc = _decimal_from_any(
        payment_snapshot.get("deposit_amount_ttc"),
        _decimal_from_any(deposit_data.get("amount_ttc"), Decimal("0.00")),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if deposit_amount_ttc <= Decimal("0.00"):
        deposit_enabled = False
        deposit_amount_ttc = Decimal("0.00")
    total_after_adjustment = _decimal_from_any(payment_snapshot.get("total_ttc_after_adjustment"), quote.total_ttc)
    if deposit_amount_ttc > total_after_adjustment:
        deposit_amount_ttc = total_after_adjustment
    remaining_ttc_after_deposit = _decimal_from_any(
        payment_snapshot.get("remaining_ttc_after_deposit"),
        total_after_adjustment - deposit_amount_ttc,
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if remaining_ttc_after_deposit < Decimal("0.00"):
        remaining_ttc_after_deposit = Decimal("0.00")

    calendar_snapshot = _calendar_snapshot_with_line_recommendation_keys(
        db,
        _json_object(quote.calendar_snapshot),
        lines=lines,
    )
    calendar_snapshot = _calendar_snapshot_with_planning_sessions(db, calendar_snapshot)
    calendar_solfege = _json_object(calendar_snapshot.get("solfege"))
    solfege_selected_slot = _json_object(calendar_solfege.get("selected_slot"))
    selected_solfege_slot = _json_object(quote.selected_solfege_slot)
    if not selected_solfege_slot:
        selected_solfege_slot = solfege_selected_slot

    calendar_snapshot = _calendar_snapshot_with_current_solfege_block(
        calendar_snapshot,
        db=db,
        quote=quote,
        lines=lines,
        selected_solfege_slot=selected_solfege_slot,
        language=language,
    )
    pending_solfege_info = _solfege_pending_block_info(calendar_snapshot, db=db, language=language)
    current_solfege_info = _current_solfege_document_info(
        lines=lines,
        calendar_snapshot=calendar_snapshot,
        quote_selected_slot=selected_solfege_slot,
        quote_level=quote.estimated_solfege_level,
        quote_duration_minutes=quote.solfege_duration_minutes,
        language=language,
    )
    has_current_solfege = bool(current_solfege_info.get("has_current_solfege"))
    current_solfege_slot = _json_object(current_solfege_info.get("selected_slot"))
    if has_current_solfege:
        selected_solfege_slot = current_solfege_slot
    else:
        selected_solfege_slot = {}
    current_solfege_level = str(current_solfege_info.get("level_code") or "").strip()
    current_solfege_duration = current_solfege_info.get("duration_minutes")
    activity_solfege = [item for item in _json_list(meta.get("activity_solfege")) if isinstance(item, dict)]
    masterclass_blocks_meta = [item for item in _json_list(meta.get("masterclass_blocks")) if isinstance(item, dict)]
    masterclass_blocks_calendar = _masterclass_blocks_from_calendar_snapshot(calendar_snapshot, language=language)
    masterclass_blocks = [*masterclass_blocks_meta, *masterclass_blocks_calendar]
    masterclass_blocks_deduped: list[dict[str, Any]] = []
    seen_masterclass: set[tuple[str, str, str]] = set()
    for item in masterclass_blocks:
        key = (
            str(item.get("session") or "").strip().lower(),
            str(item.get("location_label") or "").strip().lower(),
            str(item.get("activity_label") or "").strip().lower(),
        )
        if key in seen_masterclass:
            continue
        seen_masterclass.add(key)
        masterclass_blocks_deduped.append(item)
    masterclass_blocks = masterclass_blocks_deduped
    pass_recup_mode = str(meta.get("pass_recup_mode") or "").strip().lower() or "auto"
    pass_recup_allowed = not _quote_template_disables_pass_recup(db=db, quote=quote)
    pass_recup_enabled = pass_recup_allowed and _resolve_pass_recup_enabled(meta=meta, lines=lines)

    has_pending_solfege = bool(pending_solfege_info.get("has_pending_selection"))
    solfege_enabled = bool(has_current_solfege or activity_solfege or has_pending_solfege)
    if solfege_enabled and current_solfege_duration is None:
        current_solfege_duration = quote.solfege_duration_minutes
    if not solfege_enabled:
        current_solfege_level = ""
        current_solfege_duration = None
        selected_solfege_slot = {}
    masterclass_enabled = (
        bool(masterclass_blocks)
        or _is_true(meta.get("masterclass_enabled"))
        or any(_line_matches_masterclass(line) for line in lines)
    )
    end_year_concert_allowed = _quote_template_allows_end_year_concert(db=db, quote=quote)
    end_year_concert_enabled = end_year_concert_allowed and (
        _is_true(meta.get("end_year_concert_enabled"))
        or _is_true(meta.get("concert_enabled"))
        or any(_line_matches_end_year_concert(line) for line in lines)
    )

    payment_method_code = str(payment_snapshot.get("payment_method") or "").strip().upper()
    schedule_allowed_for_audience = bool(schedule_visibility.get(audience, False))
    show_schedule_detailed = has_installment_schedule and schedule_allowed_for_audience
    payment_schedule_compact_notice = ""
    if schedule and not show_schedule_detailed and payment_method_code != CARD_4X_FEES_PAYMENT_METHOD:
        if len(schedule) == 1:
            payment_schedule_compact_notice = _quote_doc_text(
                "compact_notice_one",
                language=language,
                due_label=_schedule_due_label(schedule[0], language=language),
            )
        else:
            payment_schedule_compact_notice = _quote_doc_text(
                "compact_notice_many",
                language=language,
                count=len(schedule),
            )
    payment_instruction = str(payment_snapshot.get("payment_instruction") or "").strip()
    if payment_method_code == CARD_4X_FEES_PAYMENT_METHOD and not payment_instruction:
        payment_instruction = CARD_4X_FEES_PAYMENT_INSTRUCTION

    prospect_type = str(prospect_data.get("prospect_type") or "adult").strip().lower()
    show_child_block = prospect_type == "child"
    show_adult_block = not show_child_block

    display_flags: dict[str, bool] = {
        "showAdultBlock": show_adult_block,
        "showChildBlock": show_child_block,
        "showPaymentMethodBlock": True,
        "showPaymentScheduleDetailed": show_schedule_detailed,
        "showPaymentScheduleCompactNotice": bool(payment_schedule_compact_notice),
        "showDepositBlock": deposit_enabled and deposit_amount_ttc > Decimal("0.00"),
        "showSolfegeSection": solfege_enabled,
        "showSolfegeCompactNotice": not solfege_enabled,
        "showMasterclassSection": masterclass_enabled,
        "showMasterclassCompactNotice": not masterclass_enabled,
        "showEndYearConcertSection": end_year_concert_enabled,
        "showEndYearConcertCompactNotice": end_year_concert_allowed and not end_year_concert_enabled,
        "showPassRecupSection": pass_recup_enabled,
        "showPassRecupCompactNotice": pass_recup_allowed and not pass_recup_enabled,
    }
    return {
        "audience": audience,
        "prospect_type": prospect_type,
        "schedule": schedule,
        "schedule_visibility": schedule_visibility,
        "payment_method": payment_method_code,
        "payment_method_label": _resolve_payment_method_label(quote=quote),
        "calendar_snapshot": calendar_snapshot,
        "payment_schedule_compact_notice": payment_schedule_compact_notice,
        "payment_instruction": payment_instruction,
        "deposit_enabled": deposit_enabled and deposit_amount_ttc > Decimal("0.00"),
        "deposit_amount_ttc": deposit_amount_ttc,
        "remaining_ttc_after_deposit": remaining_ttc_after_deposit,
        "solfege_enabled": solfege_enabled,
        "solfege_level": str(
            current_solfege_level
            or pending_solfege_info.get("level_code")
            or (quote.estimated_solfege_level if solfege_enabled else "")
            or ""
        ).strip(),
        "solfege_duration_minutes": current_solfege_duration,
        "solfege_selected_slot": selected_solfege_slot,
        "solfege_pending_selection": bool(pending_solfege_info.get("has_pending_selection")),
        "solfege_available_slots": [item for item in pending_solfege_info.get("slot_labels", []) if isinstance(item, str)],
        "masterclass_enabled": masterclass_enabled,
        "masterclass_blocks": masterclass_blocks,
        "end_year_concert_allowed": end_year_concert_allowed,
        "end_year_concert_enabled": end_year_concert_enabled,
        "pass_recup_mode": pass_recup_mode,
        "pass_recup_allowed": pass_recup_allowed,
        "pass_recup_enabled": pass_recup_enabled,
        "display_flags": display_flags,
        "prospect_data": prospect_data,
        "client_data": client_data,
    }


def build_quote_document_context(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> dict[str, Any]:
    context = _extract_document_context(db=db, quote=quote, lines=lines, audience=audience)
    visible_blocks: list[str] = []
    hidden_blocks: list[str] = []
    for block_name, flag_key in (
        ("adult_identity", "showAdultBlock"),
        ("child_parent_identity", "showChildBlock"),
        ("payment_method", "showPaymentMethodBlock"),
        ("payment_schedule_detailed", "showPaymentScheduleDetailed"),
        ("payment_schedule_compact_notice", "showPaymentScheduleCompactNotice"),
        ("solfege", "showSolfegeSection"),
        ("solfege_compact_notice", "showSolfegeCompactNotice"),
        ("masterclass", "showMasterclassSection"),
        ("masterclass_compact_notice", "showMasterclassCompactNotice"),
        ("end_year_concert", "showEndYearConcertSection"),
        ("end_year_concert_compact_notice", "showEndYearConcertCompactNotice"),
        ("pass_recup", "showPassRecupSection"),
        ("pass_recup_compact_notice", "showPassRecupCompactNotice"),
    ):
        if bool(context["display_flags"].get(flag_key)):
            visible_blocks.append(block_name)
        else:
            hidden_blocks.append(block_name)
    context["visible_blocks"] = visible_blocks
    context["hidden_blocks"] = hidden_blocks
    return context


TOKEN_RE = re.compile(r"\{[\s\xa0]*([a-zA-Z0-9_]+)[\s\xa0]*\}")


def _apply_template(
    template: str,
    *,
    values: dict[str, str],
    html_keys: set[str],
    html_output: bool,
) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        raw_value = values.get(key, "")
        if html_output:
            if key in html_keys:
                return raw_value
            return escape(raw_value)
        return raw_value

    return TOKEN_RE.sub(repl, template)


def _normalize_block_placeholder_wrappers(template: str, *, keys: set[str]) -> str:
    raw = str(template or "")
    if not raw or not keys:
        return raw
    normalized = raw
    for key in keys:
        key_pattern = r"\{[\s\xa0]*" + re.escape(key) + r"[\s\xa0]*\}"
        for tag in ("p", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6"):
            normalized = re.sub(
                rf"<{tag}\b[^>]*>\s*{key_pattern}\s*</{tag}>",
                "{" + key + "}",
                normalized,
                flags=re.IGNORECASE | re.DOTALL,
            )
            normalized = re.sub(
                rf"<{tag}\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*{key_pattern}(?:\s*(?:<br\s*/?>|&nbsp;))*\s*</{tag}>",
                "{" + key + "}",
                normalized,
                flags=re.IGNORECASE | re.DOTALL,
            )
    return normalized


def _as_html_fragment(content: str) -> str:
    normalized = (content or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    if "<" in normalized and ">" in normalized:
        return normalized
    return "<p>" + "<br/>".join(line for line in normalized.split("\n")) + "</p>"


def _plain_text_paragraph_html(content: str) -> str:
    normalized = str(content or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    return "<p>" + "<br/>".join(escape(line.strip()) for line in normalized.split("\n") if line.strip()) + "</p>"


def _cleanup_rendered_block_markup(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw

    cleaned = raw
    patterns = (
        r"<p\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*(<div\b.*?</div>)\s*</p>",
        r"<p\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*(<table\b.*?</table>)\s*</p>",
        r"<p\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*(<section\b.*?</section>)\s*</p>",
    )
    for _ in range(3):
        previous = cleaned
        for pattern in patterns:
            cleaned = re.sub(pattern, r"\1", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if cleaned == previous:
            break

    cleaned = re.sub(
        r"<p\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</p>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"<h[1-6]\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</h[1-6]>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return cleaned


def _normalize_template_source(template: str) -> str:
    raw = (template or "").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
        raw = raw[1:-1].strip()
    if any(token in raw for token in ("&lt;", "&gt;", "&#60;", "&#62;", "&#123;", "&#125;", "&#x7b;", "&#x7d;")):
        for _ in range(3):
            decoded = html_unescape(raw)
            if decoded == raw:
                break
            raw = decoded
    raw = raw.replace("\uFF5B", "{").replace("\uFF5D", "}")
    raw = raw.replace("\u00A0", " ")
    raw = raw.replace("\u200B", "").replace("\u200C", "").replace("\u200D", "")
    return raw


def _strip_legacy_recipient_email_markup(template: str) -> str:
    raw = str(template or "")
    if re.search(r"\{[\s\xa0]*recipient_email[\s\xa0]*\}", raw, flags=re.IGNORECASE) is None:
        return raw

    paragraph_pattern = re.compile(
        r"<p\b[^>]*>.*?\{[\s\xa0]*recipient_email[\s\xa0]*\}.*?</p>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def _replace_paragraph(match: re.Match[str]) -> str:
        block = match.group(0)
        plain = re.sub(r"<[^>]+>", " ", block, flags=re.IGNORECASE)
        plain = re.sub(r"\{\s*recipient_email\s*\}", " ", plain, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+", " ", html_unescape(plain)).strip().lower()

        if "destinataire" in normalized:
            updated = re.sub(r"\s*\(\s*\{recipient_email\}\s*\)", "", block, flags=re.IGNORECASE)
            updated = re.sub(r"\s*[-–—,:]\s*\{recipient_email\}", "", updated, flags=re.IGNORECASE)
            updated = re.sub(r"\{\s*recipient_email\s*\}", "", updated, flags=re.IGNORECASE)
            return updated

        if "email" in normalized or "contact" in normalized:
            return ""

        return re.sub(r"\{\s*recipient_email\s*\}", "", block, flags=re.IGNORECASE)

    cleaned = paragraph_pattern.sub(_replace_paragraph, raw)
    cleaned = re.sub(r"\s*\(\s*\{recipient_email\}\s*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[-–—,:]\s*\{recipient_email\}", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\{\s*recipient_email\s*\}", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _dedupe_retained_activities_tables(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw

    pattern = re.compile(
        r"(<h[1-3][^>]*>\s*Les\s+Activites?\s+retenues\s*</h[1-3]>\s*)"
        r"(<table\b.*?</table>\s*)"
        r"(<table\b.*?</table>)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def _replace(match: re.Match[str]) -> str:
        heading = match.group(1)
        first_table = match.group(2)
        second_table = match.group(3)
        first_is_services = bool(
            re.search(r"<th[^>]*>\s*Activite\s*</th>", first_table, flags=re.IGNORECASE)
            and not re.search(r"<th[^>]*>\s*Type\s+activite\s*</th>", first_table, flags=re.IGNORECASE)
        )
        second_is_planning = bool(
            re.search(r"<th[^>]*>\s*Type\s+activite\s*</th>", second_table, flags=re.IGNORECASE)
            and re.search(r"<th[^>]*>\s*Lieu\s*</th>", second_table, flags=re.IGNORECASE)
        )
        if first_is_services and second_is_planning:
            return f"{heading}{second_table}"
        return match.group(0)

    return pattern.sub(_replace, raw)


def _cleanup_legacy_terms_layout(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw
    has_table = "<table" in raw.lower()
    if not has_table:
        return raw
    has_table_headers = "<th" in raw.lower()
    table_count = len(re.findall(r"<table\b", raw, flags=re.IGNORECASE))
    if has_table_headers or table_count != 1:
        return raw

    row_pattern = re.compile(
        r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*</tr>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    rows = row_pattern.findall(raw)
    if len(rows) < 4:
        return raw

    flattened = "".join(f"<p>{cell.strip()}</p>" for cell in rows if cell.strip())
    if not flattened:
        return raw
    return flattened


def _enforce_family_page_break(content: str) -> str:
    marker = "quote-page-break"
    pattern = re.compile(r"(<h[1-3][^>]*>\s*Informations?\s+(de\s+la\s+)?famille\s*</h[1-3]>)", re.IGNORECASE)
    match = pattern.search(content or "")
    if match is None:
        return content
    prefix = (content or "")[max(0, match.start() - 260):match.start()]
    if marker in prefix:
        return content
    return (content or "")[:match.start()] + "<div class='quote-page-break'></div>" + (content or "")[match.start():]


def _ensure_full_html_document(content: str) -> str:
    candidate = (content or "").strip()
    if not candidate:
        return "<html><body><p>Quote</p></body></html>"
    if "<html" in candidate.lower():
        return candidate
    return f"<html><body>{candidate}</body></html>"


def _normalize_css_vars_for_pdf(html_document: str) -> str:
    def replace(match: re.Match[str]) -> str:
        variable_name = (match.group(1) or "").strip().lower()
        explicit_fallback = (match.group(2) or "").strip()
        if explicit_fallback:
            return explicit_fallback
        return CSS_VAR_DEFAULTS.get(variable_name, "inherit")

    return CSS_VAR_RE.sub(replace, html_document)


def _render_html_pdf_with_xhtml2pdf(rendered_html: str) -> bytes | None:
    html_document = _normalize_css_vars_for_pdf(_ensure_full_html_document(rendered_html))
    output = io.BytesIO()
    try:
        status = pisa.CreatePDF(src=html_document, dest=output, encoding="utf-8")
    except Exception:
        logger.exception("Quote HTML PDF rendering crashed; falling back to block renderer")
        return None
    if status.err:
        logger.warning("Quote HTML PDF rendering failed; falling back to block renderer")
        return None
    return output.getvalue()


_INLINE_FOOTER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-footer[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)

_INLINE_RUNNING_FOOTER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-running-footer[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)


_INLINE_HEADER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-header[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)

_INLINE_RUNNING_HEADER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-running-header[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)


_INLINE_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", flags=re.IGNORECASE | re.DOTALL)


def _strip_inline_footers(content: str) -> str:
    without_table = _INLINE_FOOTER_RE.sub("", content or "")
    return _INLINE_RUNNING_FOOTER_RE.sub("", without_table)


def _strip_inline_headers(content: str) -> str:
    without_table = _INLINE_HEADER_RE.sub("", content or "")
    return _INLINE_RUNNING_HEADER_RE.sub("", without_table)


def _strip_overriding_page_styles(content: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        style_body = match.group(1) or ""
        if "@page" in style_body.lower():
            return ""
        return match.group(0)

    return _INLINE_STYLE_RE.sub(_replace, content or "")


def _strip_inline_style_blocks(content: str) -> str:
    return _INLINE_STYLE_RE.sub("", content or "")


def _extract_body_inner_html(content: str) -> str:
    raw = str(content or "")
    matched = re.search(r"<body[^>]*>(.*)</body>", raw, flags=re.IGNORECASE | re.DOTALL)
    if matched is None:
        return raw
    return matched.group(1)


def _normalize_tables_for_pdf(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw

    def _normalize_table_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        lowered = tag.lower()
        if (
            "quote-running-header" in lowered
            or "quote-running-footer" in lowered
            or "quote-header" in lowered
            or "quote-footer" in lowered
        ):
            return tag

        updated = tag
        class_match = re.search(r"class\s*=\s*(['\"])(.*?)\1", updated, flags=re.IGNORECASE | re.DOTALL)
        if class_match:
            classes = class_match.group(2)
            if "quote-table" not in classes.split():
                next_classes = f"{classes} quote-table".strip()
                updated = (
                    updated[: class_match.start(2)]
                    + next_classes
                    + updated[class_match.end(2) :]
                )
        else:
            updated = updated[:-1] + " class='quote-table'>"

        if not re.search(r"\bcellpadding\s*=", updated, flags=re.IGNORECASE):
            updated = updated[:-1] + " cellpadding='10'>"
        if not re.search(r"\bcellspacing\s*=", updated, flags=re.IGNORECASE):
            updated = updated[:-1] + " cellspacing='0'>"
        return updated

    def _append_style(existing: str) -> str:
        base = existing.strip()
        if base and not base.endswith(";"):
            base = base + ";"
        extra = (
            "padding:12px 10px 12px 10px;"
            "padding-top:12px;"
            "padding-right:10px;"
            "padding-bottom:12px;"
            "padding-left:10px;"
            "vertical-align:middle;"
        )
        return (base + extra).strip()

    def _normalize_cell_tag(match: re.Match[str]) -> str:
        tag_name = match.group(1)
        attrs = match.group(2) or ""
        updated_attrs = attrs

        style_match = re.search(r"style\s*=\s*(['\"])(.*?)\1", updated_attrs, flags=re.IGNORECASE | re.DOTALL)
        if style_match:
            next_style = _append_style(style_match.group(2))
            updated_attrs = (
                updated_attrs[: style_match.start(2)]
                + next_style
                + updated_attrs[style_match.end(2) :]
            )
        else:
            updated_attrs = f"{updated_attrs} style='{_append_style('')}'"

        if not re.search(r"\bvalign\s*=", updated_attrs, flags=re.IGNORECASE):
            updated_attrs = f"{updated_attrs} valign='middle'"

        return f"<{tag_name}{updated_attrs}>"

    normalized = re.sub(r"<table\b[^>]*>", _normalize_table_tag, raw, flags=re.IGNORECASE)
    normalized = re.sub(r"<(th|td)([^>]*)>", _normalize_cell_tag, normalized, flags=re.IGNORECASE)
    return normalized


def _simplify_rich_text_to_pdf_paragraphs(content: str, *, values: dict[str, str], language: str | None = None) -> str:
    normalized = _normalize_template_source(content or "")
    if not normalized:
        return f"<p>{escape(_quote_doc_text('terms_empty', language=language))}</p>"
    substituted = _apply_template(normalized, values=values, html_keys=set(), html_output=False)
    raw = str(substituted or "")
    raw = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)<li\b[^>]*>", "• ", raw)
    raw = re.sub(r"(?i)</(p|div|section|h[1-6]|li|tr|table|ul|ol)>", "\n", raw)
    raw = re.sub(r"(?i)</(td|th)>", "  ", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_unescape(raw)
    raw = raw.replace("\r", "")
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if not lines:
        return f"<p>{escape(_quote_doc_text('terms_empty', language=language))}</p>"
    return "".join(f"<p>{escape(line)}</p>" for line in lines)


def _build_quote_pdf_blocks_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str,
) -> str:
    values, html_keys, _ = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    language = _quote_doc_language(quote=quote)
    cgv_label, cgv_content = _load_terms_template_content(db=db, quote=quote)
    cgv_content = _localized_english_text_fragments(cgv_content, language=language)
    terms_html = _simplify_rich_text_to_pdf_paragraphs(cgv_content, values=values, language=language)

    template = (
        "<section class='quote-block'>"
        "<h1>{cover_title}</h1>"
        "<p><strong>{cover_quote} :</strong> {quote_number}</p>"
        "<p><strong>{cover_school_year} :</strong> {school_year_label}</p>"
        "<p><strong>{quote_status_date_label} :</strong> {quote_status_date_value}</p>"
        "<p><strong>{cover_student} :</strong> {child_full_name}</p>"
        "</section>"
        "{page_break_html}"
        "<h2>{identity_title}</h2>"
        "<div class='quote-block'>{prospect_identity_block_html}</div>"
        "{page_break_html}"
        "<h2>{section_courses_options}</h2>"
        "{activities_planning_table_html}"
        "{services_section_html}"
        "{adjustments_section_html}"
        "{products_section_html}"
        "{kits_section_html}"
        "{other_fees_section_html}"
        "{financial_recap_block_html}"
        "<h2>{payment_title}</h2>"
        "{payment_method_block_html}"
        "<p>{payment_schedule_summary}</p>"
        "{payment_schedule_table_html}"
        "{options_section_html}"
        "{page_break_html}"
        "<h2>{calendar_title}</h2>"
        "<p><strong>{calendar_overview_label} :</strong> {calendar_summary}</p>"
        "{calendar_activity_semesters_html}"
        "{page_break_html}"
        "<h2>{terms_title}</h2>"
        "<div class='quote-block'>"
        "<p><strong>{cgv_version}</strong></p>"
        "{terms_plain_pdf_html}"
        "</div>"
    )
    block_values = dict(values)
    block_values["cgv_version"] = cgv_label or values.get("cgv_version", _quote_doc_text("terms_version_unspecified", language=language))
    block_values["terms_plain_pdf_html"] = terms_html
    local_html_keys = set(html_keys)
    local_html_keys.add("terms_plain_pdf_html")
    rendered = _apply_template(template, values=block_values, html_keys=local_html_keys, html_output=True)
    rendered = _cleanup_rendered_block_markup(rendered)
    rendered = _normalize_tables_for_pdf(rendered)
    return rendered


def _pdf_shell_html(*, content_html: str, header_html: str, footer_html: str) -> str:
    return (
        "<html><head><meta charset='utf-8'/>"
        "<style>"
        "@page {"
        "  size: a4 portrait;"
        "  margin: 0;"
        "  @frame header_frame { -pdf-frame-content: header_content; left: 36pt; top: 14pt; width: 523pt; height: 44pt; }"
        "  @frame content_frame { left: 36pt; top: 64pt; width: 523pt; height: 700pt; }"
        "  @frame footer_frame { -pdf-frame-content: footer_content; left: 36pt; top: 770pt; width: 523pt; height: 58pt; }"
        "}"
        "body{font-family:Arial,Helvetica,sans-serif;color:#1f1f1f;font-size:11px;line-height:1.42;}"
        "h1,h2,h3{color:#101828;margin:0 0 8px 0;}"
        "p{margin:0 0 7px 0;}"
        ".quote-page-break{page-break-before:always;}"
        ".quote-block{border:1px solid #d4dae3;background:#fbfcfe;padding:10px;margin:0 0 10px 0;page-break-inside:auto;}"
        ".quote-content table,.quote-table{width:100%;border-collapse:collapse;border-spacing:0;table-layout:auto;margin:8px 0 12px 0;font-size:10.9px;}"
        ".quote-content th,.quote-table th{background:#e7edf7 !important;color:#111827 !important;border:1px solid #c2ccda !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;text-align:left !important;font-weight:700 !important;line-height:1.4 !important;vertical-align:middle !important;white-space:normal !important;word-break:break-word !important;overflow-wrap:anywhere !important;height:auto !important;min-height:30px;}"
        ".quote-content td,.quote-table td{border:1px solid #d3dbe7 !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;vertical-align:middle !important;color:#111827 !important;line-height:1.45 !important;word-break:break-word !important;white-space:normal !important;overflow-wrap:anywhere !important;height:auto !important;min-height:30px;}"
        ".quote-content td>*{margin-top:0 !important;margin-bottom:0 !important;}"
        ".quote-content font[size='10'],font[size='10']{font-size:10px !important;line-height:1.45 !important;color:#6b7280 !important;}"
        ".quote-content thead,thead{display:table-header-group !important;}"
        ".quote-content tfoot,tfoot{display:table-footer-group !important;}"
        ".quote-content tr,tr{page-break-inside:auto !important;break-inside:auto !important;height:auto !important;}"
        ".quote-brand-logo-img{display:inline-block;max-width:120px;max-height:34px;object-fit:contain;}"
        ".quote-running-header{width:100%;border-collapse:collapse;font-size:10px;color:#334155;border-bottom:1px solid #d7dee8;}"
        ".quote-running-header td{vertical-align:middle;padding:0 0 4px 0;}"
        ".quote-running-footer{width:100%;border-collapse:collapse;font-size:9.4px;color:#475467;border-top:1px solid #d7dee8;}"
        ".quote-running-footer td{vertical-align:top;padding-top:5px;line-height:1.35;}"
        "</style>"
        "</head><body>"
        "<div id='header_content'>"
        f"{header_html}"
        "</div>"
        "<div id='footer_content'>"
        f"{footer_html}"
        "</div>"
        "<div class='quote-content'>"
        f"{content_html}"
        "</div>"
        "</body></html>"
    )


def _build_template_values(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> tuple[dict[str, str], set[str], dict[str, Any]]:
    language = _quote_doc_language(quote=quote)
    currency = (quote.currency or "EUR").upper()
    calendar_snapshot = _calendar_snapshot_with_planning_sessions(db, _json_object(quote.calendar_snapshot))
    service_product_ids = _service_product_ids_for_lines(db=db, lines=lines)
    services, products, kits, adjustments, other_fees = _line_groups(lines, service_product_ids=service_product_ids)
    document_context = build_quote_document_context(db=db, quote=quote, lines=lines, audience=audience)
    calendar_snapshot = _json_object(document_context.get("calendar_snapshot")) or calendar_snapshot
    display_flags = document_context["display_flags"]
    selected_solfege_slot = _json_object(document_context.get("solfege_selected_slot"))
    total_ttc = Decimal(quote.total_ttc or 0).quantize(Decimal("0.01"))
    total_ht_before_from_lines = sum(
        (Decimal(getattr(line, "amount_ht", Decimal("0")) or Decimal("0")) for line in lines),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    vat_amount_before_from_lines = sum(
        (Decimal(getattr(line, "amount_vat", Decimal("0")) or Decimal("0")) for line in lines),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    vat_rate = _resolve_display_vat_rate(
        quote=quote,
        lines=lines,
        total_ht=total_ht_before_from_lines,
        total_vat=vat_amount_before_from_lines,
    )

    payment_terms_snapshot = _json_object(quote.payment_terms_snapshot)
    adjustment_data = _json_object(payment_terms_snapshot.get("adjustment"))
    if not adjustment_data:
        adjustment_data = _json_object(_json_object(quote.meta).get("financial_adjustment"))
    adjustment_type = str(adjustment_data.get("type") or "").strip().lower()
    if adjustment_type not in {"credit", "debt"}:
        adjustment_type = "none"
    adjustment_amount = _decimal_from_any(adjustment_data.get("amount_ttc"), Decimal("0")).quantize(Decimal("0.01"))
    if adjustment_amount <= Decimal("0"):
        adjustment_amount = Decimal("0.00")
        adjustment_type = "none"
    adjustment_signed_amount = (
        -adjustment_amount
        if adjustment_type == "credit"
        else adjustment_amount
        if adjustment_type == "debt"
        else Decimal("0.00")
    )
    total_before_adjustment = (total_ttc - adjustment_signed_amount).quantize(Decimal("0.01"))
    total_after_adjustment = total_ttc
    schedule = [item for item in _json_list(document_context.get("schedule")) if isinstance(item, dict)]
    has_deposit = bool(document_context.get("deposit_enabled"))
    deposit_amount_ttc = _decimal_from_any(document_context.get("deposit_amount_ttc"), Decimal("0.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if deposit_amount_ttc <= Decimal("0.00"):
        has_deposit = False
        deposit_amount_ttc = Decimal("0.00")
    if deposit_amount_ttc > total_after_adjustment:
        deposit_amount_ttc = total_after_adjustment
    remaining_ttc_after_deposit = _decimal_from_any(
        document_context.get("remaining_ttc_after_deposit"),
        total_after_adjustment - deposit_amount_ttc,
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if remaining_ttc_after_deposit < Decimal("0.00"):
        remaining_ttc_after_deposit = Decimal("0.00")
    adjustment_effective_date = _birth_date_label(str(adjustment_data.get("effective_date") or ""))
    adjustment_label = str(adjustment_data.get("label") or "").strip()
    adjustment_type_label = (
        _quote_doc_text("financial_adjustment_credit", language=language)
        if adjustment_type == "credit"
        else _quote_doc_text("financial_adjustment_debt", language=language)
        if adjustment_type == "debt"
        else _quote_doc_text("financial_adjustment_none", language=language)
    )
    adjustment_impact_label = (
        _quote_doc_text("financial_adjustment_credit_impact", language=language)
        if adjustment_type == "credit"
        else _quote_doc_text("financial_adjustment_debt_impact", language=language)
        if adjustment_type == "debt"
        else ""
    )
    adjustment_display_title = adjustment_type_label if adjustment_type != "none" else ""
    adjustment_display_line = (
        f"{adjustment_display_title} : {_money(adjustment_amount, currency)}"
        if adjustment_type != "none"
        else ""
    )
    has_financial_adjustment = adjustment_type in {"credit", "debt"}
    has_credit_adjustment = adjustment_type == "credit"
    has_debt_adjustment = adjustment_type == "debt"

    total_ht_before_adjustment = total_ht_before_from_lines
    vat_amount_before_adjustment = vat_amount_before_from_lines
    if adjustment_type == "none":
        total_ht_after_adjustment = total_ht_before_from_lines
        vat_amount_after_adjustment = vat_amount_before_from_lines
    else:
        total_ht_after_adjustment, vat_amount_after_adjustment = _split_ttc_with_rate(total_after_adjustment, vat_rate)
    remaining_ht_after_deposit, remaining_vat_after_deposit = _split_ttc_with_rate(remaining_ttc_after_deposit, vat_rate)
    deposit_ht_amount, deposit_vat_amount = _split_ttc_with_rate(deposit_amount_ttc, vat_rate)

    if adjustment_type == "none":
        financial_adjustment_block_html = ""
        financial_adjustment_section_html = ""
        financial_adjustment_none_html = f"<p>{escape(_quote_doc_text('financial_adjustment_none_html', language=language))}</p>"
        total_ttc_before_adjustment_html = ""
    else:
        adjustment_parts = [
            f"<p><strong>{escape(adjustment_display_title)}</strong> : {escape(_money(adjustment_amount, currency))}</p>",
            f"<p><strong>{escape(_quote_doc_text('financial_impact', language=language))}:</strong> {escape(adjustment_impact_label)}</p>",
        ]
        if adjustment_effective_date and adjustment_effective_date != "-":
            adjustment_parts.append(f"<p><strong>{escape(_quote_doc_text('financial_adjustment_date', language=language))}:</strong> {escape(adjustment_effective_date)}</p>")
        normalized_adjustment_label = adjustment_label.strip().lower()
        normalized_type_label = adjustment_type_label.strip().lower()
        if (
            adjustment_label
            and normalized_adjustment_label not in {"avoir", "dette"}
            and normalized_adjustment_label != normalized_type_label
        ):
            adjustment_parts.append(f"<p><strong>{escape(_quote_doc_text('financial_label', language=language))}:</strong> {escape(adjustment_label)}</p>")
        financial_adjustment_block_html = "".join(adjustment_parts)
        # Keep this block content-only (no heading) so it can be safely inserted in WYSIWYG flows.
        financial_adjustment_section_html = financial_adjustment_block_html
        financial_adjustment_none_html = ""
        total_ttc_before_adjustment_html = (
            f"<p><strong>{escape(_quote_doc_text('financial_total_before_adjustment', language=language))} :</strong> {_decimal_str(total_before_adjustment)} {escape(currency)}</p>"
        )
    if adjustment_type == "none":
        financial_recap_rows: list[tuple[str, str]] = [
            (_quote_doc_text("financial_total_ht", language=language), f"{_decimal_str(total_ht_after_adjustment)} {currency}"),
            (_quote_doc_text("financial_vat", language=language, rate=_decimal_str(vat_rate)), f"{_decimal_str(vat_amount_after_adjustment)} {currency}"),
            (_quote_doc_text("financial_total_ttc_quote", language=language), f"{_decimal_str(total_after_adjustment)} {currency}"),
        ]
    else:
        financial_recap_rows = [
            (_quote_doc_text("financial_total_before_adjustment", language=language), f"{_decimal_str(total_before_adjustment)} {currency}"),
            (adjustment_display_title, f"{_decimal_str(adjustment_amount)} {currency}"),
            (_quote_doc_text("financial_impact", language=language), adjustment_impact_label),
        ]
        if adjustment_effective_date and adjustment_effective_date != "-":
            financial_recap_rows.append((_quote_doc_text("financial_adjustment_date", language=language), adjustment_effective_date))
        financial_recap_rows.extend(
            [
                (_quote_doc_text("financial_total_ht_invoice", language=language), f"{_decimal_str(total_ht_after_adjustment)} {currency}"),
                (_quote_doc_text("financial_vat_invoice", language=language, rate=_decimal_str(vat_rate)), f"{_decimal_str(vat_amount_after_adjustment)} {currency}"),
                (_quote_doc_text("financial_total_ttc_quote", language=language), f"{_decimal_str(total_after_adjustment)} {currency}"),
            ]
        )
    if has_deposit:
        financial_recap_rows.extend(
            [
                (_quote_doc_text("financial_deposit", language=language), f"{_decimal_str(deposit_amount_ttc)} {currency}"),
                (_quote_doc_text("financial_remaining_after_deposit", language=language), f"{_decimal_str(remaining_ttc_after_deposit)} {currency}"),
                (_quote_doc_text("financial_remaining_ht", language=language), f"{_decimal_str(remaining_ht_after_deposit)} {currency}"),
                (_quote_doc_text("financial_remaining_vat", language=language, rate=_decimal_str(vat_rate)), f"{_decimal_str(remaining_vat_after_deposit)} {currency}"),
            ]
        )

    financial_recap_lines_html = "".join(
        "<p>"
        f"<strong>{escape(label)} :</strong> {escape(value)}"
        "</p>"
        for label, value in financial_recap_rows
    )
    financial_recap_block_html = (
        "<div class='quote-block'>"
        f"<h2>{escape(_quote_doc_text('financial_title', language=language))}</h2>"
        f"{financial_recap_lines_html}"
        "</div>"
    )
    if has_deposit:
        balance_due_text = ""
        if schedule and len(schedule) == 1 and remaining_ttc_after_deposit > Decimal("0.00"):
            due_label = _schedule_due_label(schedule[0], language=language)
            item_method_label = str(schedule[0].get("payment_method") or document_context.get("payment_method_label") or "").strip()
            amount = f"{_decimal_str(remaining_ttc_after_deposit)} {currency}"
            if _is_bank_transfer_payment_method(item_method_label) and due_label == _quote_doc_text("schedule_due_invoice", language=language):
                balance_due_text = _quote_doc_text("deposit_balance_bank_due", language=language, amount=amount)
            else:
                balance_due_text = _quote_doc_text("deposit_balance_due", language=language, amount=amount, due_label=due_label)
        elif remaining_ttc_after_deposit > Decimal("0.00"):
            balance_due_text = _quote_doc_text("deposit_balance_schedule", language=language)
        deposit_block_html = (
            f"<p>{escape(_quote_doc_text('deposit_confirm', language=language))}</p>"
            + (f"<p>{escape(balance_due_text)}</p>" if balance_due_text else "")
            +
            f"<p><strong>{escape(_quote_doc_text('deposit_amount_due', language=language))} :</strong> {_decimal_str(deposit_amount_ttc)} {escape(currency)}</p>"
        )
    else:
        deposit_block_html = ""
    deposit_section_html = _section_html(_quote_doc_text("deposit_section_title", language=language), deposit_block_html)
    deposit_none_html = "" if has_deposit else f"<p>{escape(_quote_doc_text('deposit_none', language=language))}</p>"

    services_table_html = _table_html(
        [
            _quote_doc_text("planning_activity", language=language),
            _quote_doc_text("table_quantity", language=language),
            _quote_doc_text("planning_duration", language=language),
            _quote_doc_text("table_vat", language=language),
            _quote_doc_text("table_unit_price_ttc", language=language),
            _quote_doc_text("table_total_ttc", language=language),
        ],
        [
            [
                _quote_line_display_title(line, language=language),
                _compact_quantity_label(line.quantity),
                f"{int(line.duration_minutes)} min" if line.duration_minutes else "-",
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in services
        ],
        empty_label=_quote_doc_text("empty_activity", language=language),
    )
    product_long_descriptions = _product_long_descriptions_by_id(db=db, products=products)
    products_table_html = _table_html(
        [
            _quote_doc_text("table_material", language=language),
            _quote_doc_text("table_quantity", language=language),
            _quote_doc_text("table_vat", language=language),
            _quote_doc_text("table_unit_price_ttc", language=language),
            _quote_doc_text("table_total_ttc", language=language),
        ],
        [
            [
                {
                    "html": (
                        f"<div>{escape(_quote_line_display_title(line, language=language))}</div>"
                        + _small_description_html(
                            _localized_catalog_text(
                                "\n".join(
                                    _unique_text_parts(
                                        line.description,
                                        product_long_descriptions.get(line.product_id),
                                    )
                                ),
                                language=language,
                            )
                        )
                    )
                },
                _compact_quantity_label(line.quantity),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in products
        ],
        empty_label=_quote_doc_text("empty_material", language=language),
    )
    kit_long_descriptions = _kit_long_descriptions_by_id(db=db, kits=kits)
    kit_composition = _kit_composition_by_id(db=db, kits=kits, language=language)
    kits_table_html = _table_html(
        [
            _quote_doc_text("table_kit", language=language),
            _quote_doc_text("table_quantity", language=language),
            _quote_doc_text("table_vat", language=language),
            _quote_doc_text("table_unit_price_ttc", language=language),
            _quote_doc_text("table_total_ttc", language=language),
        ],
        [
            [
                {
                    "html": (
                        f"<div>{escape(_quote_line_display_title(line, language=language))}</div>"
                        + _small_description_html(
                            _localized_catalog_text(
                                "\n".join(
                                    _unique_text_parts(
                                        line.description,
                                        kit_long_descriptions.get(line.kit_id),
                                    )
                                ),
                                language=language,
                            )
                        )
                        + _kit_composition_html(kit_composition.get(line.kit_id, []), language=language)
                    )
                },
                _compact_quantity_label(line.quantity),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in kits
        ],
        empty_label=_quote_doc_text("empty_kit", language=language),
    )
    adjustments_table_html = _table_html(
        [
            _quote_doc_text("table_type", language=language),
            _quote_doc_text("table_title", language=language),
            _quote_doc_text("table_quantity", language=language),
            _quote_doc_text("table_vat", language=language),
            _quote_doc_text("table_unit_price_ttc", language=language),
            _quote_doc_text("table_total_ttc", language=language),
        ],
        [
            [
                _quote_doc_text("fee_discount", language=language)
                if (line.line_type or "").strip().lower() == "discount"
                else _quote_doc_text("fee_surcharge", language=language)
                if (line.line_type or "").strip().lower() == "surcharge"
                else (
                    _quote_doc_text("fee_discount", language=language)
                    if (line.master_item_type or "").strip().lower() == "discount_rule"
                    else _quote_doc_text("fee_surcharge", language=language)
                ),
                _quote_line_display_title(line, language=language),
                _compact_quantity_label(line.quantity),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in adjustments
        ],
        empty_label=_quote_doc_text("empty_adjustment", language=language),
    )
    other_fees_table_html = _table_html(
        [
            _quote_doc_text("table_title", language=language),
            _quote_doc_text("table_quantity", language=language),
            _quote_doc_text("table_vat", language=language),
            _quote_doc_text("table_unit_price_ttc", language=language),
            _quote_doc_text("table_total_ttc", language=language),
        ],
        [
            [
                _quote_line_display_title(line, language=language),
                _compact_quantity_label(line.quantity),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in other_fees
        ],
        empty_label=_quote_doc_text("empty_other_fee", language=language),
    )
    lines_table_html = _table_html(
        [
            _quote_doc_text("table_category", language=language),
            _quote_doc_text("table_title", language=language),
            _quote_doc_text("table_quantity", language=language),
            _quote_doc_text("table_vat", language=language),
            _quote_doc_text("table_unit_price_ttc", language=language),
            _quote_doc_text("table_total_ttc", language=language),
        ],
        [
            [
                _quote_doc_text("fee_discount", language=language)
                if (line.line_type or "").strip().lower() == "discount"
                else _quote_doc_text("fee_surcharge", language=language)
                if (line.line_type or "").strip().lower() == "surcharge"
                else (
                    _quote_doc_text("fee_service", language=language)
                    if ((line.line_category or "").lower() == "service" or _line_is_service_fee(line, service_product_ids=service_product_ids))
                    else (_quote_doc_text("fee_kit", language=language) if line.kit_id else _quote_doc_text("fee_material", language=language))
                ),
                _quote_line_display_title(line, language=language),
                _compact_quantity_label(line.quantity),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in lines
        ],
        empty_label=_quote_doc_text("empty_lines", language=language),
    )

    schedule = document_context["schedule"]
    special_bank_transfer_deposit_lines = _bank_transfer_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        payment_method_label=str(document_context.get("payment_method_label") or _resolve_payment_method_label(quote=quote)),
        remaining_ttc_after_deposit=remaining_ttc_after_deposit,
        language=language,
    )
    special_card_deposit_lines = _card_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        payment_method_label=str(document_context.get("payment_method_label") or _resolve_payment_method_label(quote=quote)),
        remaining_ttc_after_deposit=remaining_ttc_after_deposit,
        language=language,
    )
    special_deposit_lines = special_bank_transfer_deposit_lines or special_card_deposit_lines
    check_payment_instruction_lines = _check_payment_instruction_lines(
        payment_method_label=str(document_context.get("payment_method_label") or _resolve_payment_method_label(quote=quote)),
        schedule=schedule,
        legal_entity_name=_quote_legal_entity_name(db=db, quote=quote),
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        language=language,
    )
    payment_schedule_rows = [
        [
            str(item.get("label") or "-"),
            f"{item.get('amount_ttc', '-')}" + (f" {item.get('currency')}" if item.get("currency") else ""),
            _schedule_due_label(item, language=language),
            str(item.get("payment_method") or "-"),
        ]
        for item in schedule
    ]
    payment_schedule_table_html = _table_html(
        [
            _quote_doc_text("schedule_label", language=language),
            _quote_doc_text("schedule_amount", language=language),
            _quote_doc_text("schedule_when", language=language),
            _quote_doc_text("schedule_type", language=language),
        ],
        payment_schedule_rows,
        empty_label=_quote_doc_text("schedule_empty", language=language),
    )
    if special_deposit_lines:
        payment_schedule_table_html = ""
    elif not display_flags["showPaymentScheduleDetailed"]:
        compact_notice = str(document_context["payment_schedule_compact_notice"] or "").strip()
        if schedule and len(schedule) <= 1:
            payment_schedule_table_html = ""
        elif compact_notice:
            payment_schedule_table_html = f"<p>{escape(compact_notice)}</p>"
        elif not schedule:
            payment_schedule_table_html = f"<p>{escape(_quote_doc_text('schedule_empty', language=language))}</p>"
        else:
            payment_schedule_table_html = ""

    sessions = [item for item in _json_list(calendar_snapshot.get("sessions")) if isinstance(item, dict)]
    planning_blocks_table_html, _ = _planning_blocks_table_html(
        calendar_snapshot,
        selected_solfege_slot=selected_solfege_slot,
        language=language,
    )
    calendar_sessions_table_html = _table_html(
        [
            _quote_doc_text("calendar_date", language=language),
            _quote_doc_text("calendar_start", language=language),
            _quote_doc_text("calendar_end", language=language),
            _quote_doc_text("planning_duration", language=language),
            _quote_doc_text("calendar_modality", language=language),
        ],
        [
            [
                str(item.get("date") or "-"),
                str(item.get("start_time") or item.get("start_at") or "-"),
                str(item.get("end_time") or item.get("end_at") or "-"),
                f"{item.get('duration_minutes')} min" if item.get("duration_minutes") is not None else "-",
                _modality_label(item.get("modality"), language=language) if str(item.get("modality") or "").strip() else "-",
            ]
            for item in sessions
        ],
        empty_label=_quote_doc_text("calendar_empty", language=language),
    )
    calendar_table_html, calendar_activities_count = _calendar_visual_summary(sessions, language=language)
    calendar_summary = _calendar_summary_text(
        session_count=len(sessions),
        activity_count=calendar_activities_count,
        language=language,
    )
    special_bank_transfer_deposit_lines = _bank_transfer_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        payment_method_label=str(document_context.get("payment_method_label") or _resolve_payment_method_label(quote=quote)),
        remaining_ttc_after_deposit=remaining_ttc_after_deposit,
        language=language,
    )
    payment_schedule_summary = (
        _quote_doc_text(
            "payment_deposit_invoice_without_schedule",
            language=language,
            deposit_amount=_money(deposit_amount_ttc, currency),
        )
        if has_deposit and schedule and not display_flags["showPaymentScheduleDetailed"]
        else ""
        if special_deposit_lines or str(document_context.get("payment_method") or "").strip().upper() == CARD_4X_FEES_PAYMENT_METHOD
        else _payment_schedule_summary_text(
            schedule=schedule,
            has_deposit=has_deposit,
            deposit_amount_ttc=deposit_amount_ttc,
            currency=currency,
            payment_method_label=str(document_context.get("payment_method_label") or _resolve_payment_method_label(quote=quote)),
            remaining_ttc_after_deposit=remaining_ttc_after_deposit,
            language=language,
        )
    )

    activities_planning_section_html = _section_html(
        _quote_doc_text("section_courses_options", language=language),
        planning_blocks_table_html,
    )
    services_section_html = _section_html(_quote_doc_text("section_services", language=language), services_table_html)
    adjustments_section_html = _section_html(_quote_doc_text("section_adjustments", language=language), adjustments_table_html)
    products_section_html = _section_html(_quote_doc_text("section_products", language=language), products_table_html)
    kits_section_html = _section_html(_quote_doc_text("section_kits", language=language), kits_table_html)
    other_fees_section_html = _section_html(_quote_doc_text("section_other_fees", language=language), other_fees_table_html)
    payment_schedule_section_html = _section_html(_quote_doc_text("section_schedule", language=language), payment_schedule_table_html)
    calendar_section_html = _section_html(_quote_doc_text("section_calendar", language=language), calendar_table_html)

    cgv_label, _ = _load_terms_template_content(db=db, quote=quote)
    cgv_label = _localized_english_text_fragments(cgv_label, language=language)
    prospect_data = document_context["prospect_data"]
    client_data = document_context["client_data"]
    recipient_name = (
        prospect_data.get("parent_full_name")
        or prospect_data.get("adult_full_name")
        or client_data.get("client_full_name")
        or "-"
    )
    recipient_email = (
        prospect_data.get("parent_email")
        or prospect_data.get("adult_email")
        or client_data.get("client_email")
        or "-"
    )
    payment_method_label = str(document_context["payment_method_label"] or _quote_doc_text("payment_method_unspecified", language=language))
    solfege_slot = _json_object(document_context.get("solfege_selected_slot"))
    solfege_slot_label = _slot_label(solfege_slot, language=language) if solfege_slot else ""
    solfege_duration = document_context.get("solfege_duration_minutes")
    solfege_duration_label = f" ({solfege_duration} min)" if solfege_duration else ""
    solfege_slot_suffix = f" · {solfege_slot_label}" if solfege_slot_label else ""
    solfege_available_slots = [
        _sanitize_slot_label_text(item, language=language)
        for item in _json_list(document_context.get("solfege_available_slots"))
        if str(item).strip()
    ]
    solfege_display_slots, solfege_mode_label = _factorize_slot_labels(solfege_available_slots, language=language)
    solfege_full = _quote_doc_text(
        "solfege_subscribed_summary",
        language=language,
        level=document_context.get("solfege_level") or "-",
        duration=solfege_duration_label,
        slot=solfege_slot_suffix,
    )
    show_solfege_pending_notice = bool(document_context.get("solfege_pending_selection")) and not solfege_slot_label
    masterclass_blocks = _json_list(document_context.get("masterclass_blocks"))
    masterclass_full = _quote_doc_text("masterclass_subscribed", language=language)
    if masterclass_blocks:
        labels: list[str] = []
        for block in masterclass_blocks[:3]:
            if not isinstance(block, dict):
                continue
            session = str(block.get("session") or "").strip()
            location = str(block.get("location_label") or "").strip()
            label = " · ".join(part for part in (session, location) if part)
            if label:
                labels.append(label)
        if labels:
            masterclass_full = _quote_doc_text("masterclass_subscribed_with_slots", language=language, slots="; ".join(labels))

    def _identity_row_cells(label: str, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized or normalized == "-":
            return ""
        return (
            "<tr>"
            f"<td>{escape(label)}</td>"
            f"<td>{escape(normalized)}</td>"
            "</tr>"
        )

    def _identity_card(title: str, rows: list[str], empty_label: str) -> str:
        body = "".join(row for row in rows if row)
        if not body:
            body = (
                "<tr>"
                f"<td>{escape(empty_label)}</td>"
                "<td>-</td>"
                "</tr>"
            )
        return (
            "<section class='quote-identity-card'>"
            f"<h3>{escape(title)}</h3>"
            "<table class='quote-identity-meta' cellspacing='0' cellpadding='0'>"
            f"{body}"
            "</table>"
            "</section>"
        )

    adult_email_value = prospect_data.get("adult_email") or recipient_email
    adult_phone_value = str(prospect_data.get("adult_phone") or client_data.get("client_phone") or "").strip()
    adult_address_value = str(prospect_data.get("adult_address") or client_data.get("client_address") or "").strip()

    child_birth_date_value = _birth_date_label(str(prospect_data.get("child_birth_date") or ""))
    parent_email_value = prospect_data.get("parent_email") or recipient_email
    parent_phone_value = str(prospect_data.get("parent_phone") or "").strip()
    parent_address_value = str(prospect_data.get("parent_address") or "").strip()
    responsible_name_value = str(
        prospect_data.get("parent_full_name")
        or prospect_data.get("adult_full_name")
        or recipient_name
        or "-"
    ).strip()
    responsible_email_value = str(parent_email_value or adult_email_value or "").strip()
    responsible_phone_value = str(parent_phone_value or adult_phone_value or "").strip()
    responsible_address_value = str(parent_address_value or adult_address_value or "").strip()

    child_identity_card_html = _identity_card(
        _quote_doc_text("identity_child_title", language=language),
        [
            _identity_row_cells(_quote_doc_text("identity_child", language=language), str(prospect_data.get("child_full_name") or "-")),
            _identity_row_cells(_quote_doc_text("identity_birth_date", language=language), child_birth_date_value),
        ],
        _quote_doc_text("identity_child", language=language),
    )
    responsible_identity_card_html = _identity_card(
        _quote_doc_text("identity_adult_title", language=language),
        [
            _identity_row_cells(_quote_doc_text("identity_adult_contact", language=language), responsible_name_value),
            _identity_row_cells(_quote_doc_text("identity_email", language=language), responsible_email_value),
            _identity_row_cells(_quote_doc_text("identity_phone", language=language), responsible_phone_value),
            _identity_row_cells(_quote_doc_text("identity_address", language=language), responsible_address_value),
        ],
        _quote_doc_text("identity_adult_contact", language=language),
    )
    adult_identity_card_html = _identity_card(
        _quote_doc_text("identity_adult_title", language=language),
        [
            _identity_row_cells(_quote_doc_text("identity_adult_contact", language=language), str(prospect_data.get("adult_full_name") or recipient_name or "-")),
            _identity_row_cells(_quote_doc_text("identity_email", language=language), str(adult_email_value or "")),
            _identity_row_cells(_quote_doc_text("identity_phone", language=language), adult_phone_value),
            _identity_row_cells(_quote_doc_text("identity_address", language=language), adult_address_value),
        ],
        _quote_doc_text("identity_adult_contact", language=language),
    )
    prospect_identity_block_html = (
        "<div class='quote-identity-grid'>"
        + (child_identity_card_html + responsible_identity_card_html if display_flags["showChildBlock"] else adult_identity_card_html)
        + "</div>"
    )
    # Solfege et masterclass restent des activites planning, mais on expose un resume optionnel pour le document.
    solfege_block_html = ""
    if show_solfege_pending_notice:
        solfege_lines = [
            f"<strong>{escape(_quote_doc_text('solfege_option_included', language=language))}</strong>",
            f"{escape(_quote_doc_text('solfege_estimated_level', language=language))} : {escape(str(document_context.get('solfege_level') or '-'))}{escape(solfege_duration_label)}",
            f"{escape(_quote_doc_text('solfege_slot_selected', language=language))} : {escape(_quote_doc_text('to_select', language=language))}",
        ]
        if solfege_display_slots:
            solfege_lines.append(f"{escape(_quote_doc_text('solfege_slots_available', language=language))} : {escape(' ; '.join(solfege_display_slots))}")
        if solfege_mode_label:
            solfege_lines.append(escape(solfege_mode_label))
        solfege_lines.append(escape(_solfege_included_pending_notice_text(language=language)))
        solfege_block_html = "<p>" + "<br/>".join(solfege_lines) + "</p>"
    elif display_flags["showSolfegeSection"]:
        solfege_block_html = f"<p><strong>{escape(_quote_doc_text('solfege_option_included', language=language))}</strong><br/>{escape(solfege_full)}</p>"
    masterclass_common_text = _quote_doc_text("masterclass_common_text", language=language)
    masterclass_detail_text = escape(masterclass_full) if masterclass_full else ""
    masterclass_block_html = (
        f"<p><strong>{escape(_quote_doc_text('masterclass_option_subscribed', language=language))}</strong><br/>"
        f"<i>{masterclass_detail_text}</i><br/>"
        f"<i>{escape(masterclass_common_text)}</i></p>"
        if display_flags["showMasterclassSection"]
        else ""
    )
    end_year_concert_common_text = _quote_doc_text("end_year_concert_common_text", language=language)
    end_year_concert_block_html = (
        f"<p><strong>{escape(_quote_doc_text('end_year_concert_option_subscribed', language=language))}</strong><br/>"
        f"<i>{escape(end_year_concert_common_text)}</i></p>"
        if display_flags["showEndYearConcertSection"]
        else ""
    )
    end_year_concert_compact_notice_html = (
        f"<p><strong>{escape(_quote_doc_text('end_year_concert_option_not_subscribed', language=language))}</strong><br/>"
        f"<span class='quote-small-muted'><i>{escape(end_year_concert_common_text)}</i></span></p>"
        if display_flags["showEndYearConcertCompactNotice"]
        else ""
    )
    end_year_concert_compact_notice_pdf_html = (
        f"<p><b>{escape(_quote_doc_text('end_year_concert_option_not_subscribed', language=language))}</b><br/>"
        f"<font size='9' color='#667085'><i>{escape(end_year_concert_common_text)}</i></font></p>"
        if display_flags["showEndYearConcertCompactNotice"]
        else ""
    )
    pass_recup_common_text = _quote_doc_text("pass_recup_common_text", language=language)
    pass_recup_block_html = (
        f"<p><strong>{escape(_quote_doc_text('pass_recup_option_subscribed', language=language))}</strong><br/>"
        f"<i>{escape(pass_recup_common_text)}</i></p>"
        if display_flags["showPassRecupSection"]
        else ""
    )
    pass_recup_compact_notice_html = (
        _pass_recup_compact_notice_markup(language=language)
        if display_flags["showPassRecupCompactNotice"]
        else ""
    )
    pass_recup_compact_notice_pdf_html = (
        _pass_recup_compact_notice_markup(language=language, pdf_compatible=True)
        if display_flags["showPassRecupCompactNotice"]
        else ""
    )
    options_section_html = _section_html(
        _quote_doc_text("options_title", language=language),
        "".join(
            fragment
            for fragment in (
                solfege_block_html,
                masterclass_block_html,
                end_year_concert_block_html,
                end_year_concert_compact_notice_html,
                pass_recup_block_html,
                pass_recup_compact_notice_html,
            )
            if str(fragment or "").strip()
        ),
    )
    payment_instruction = str(document_context.get("payment_instruction") or "").strip()
    payment_method_display_label = payment_method_label.lower() if special_bank_transfer_deposit_lines else payment_method_label
    payment_method_block_html = f"<p><strong>{escape(_quote_doc_text('payment_method', language=language))} :</strong> {escape(payment_method_display_label)}</p>"
    if special_deposit_lines:
        payment_method_block_html += "".join(f"<p>{escape(line)}</p>" for line in special_deposit_lines)
    if check_payment_instruction_lines:
        payment_method_block_html += "".join(f"<p>{escape(line)}</p>" for line in check_payment_instruction_lines)
    if payment_instruction:
        if str(document_context.get("payment_method") or "").strip().upper() == CARD_4X_FEES_PAYMENT_METHOD:
            payment_method_block_html += _plain_text_paragraph_html(payment_instruction)
        else:
            payment_method_block_html = (
                f"{payment_method_block_html}<p><strong>{escape(_quote_doc_text('payment_instructions', language=language))} :</strong> {escape(payment_instruction)}</p>"
            )
    quote_status_date_label, quote_status_date_value, quote_status_cover_line = _quote_status_date_display(quote)

    brand_logo_html = _brand_logo_html(db=db, variant="header")
    cover_logo_html = _brand_logo_html(db=db, variant="cover")
    header_standard_html = (
        "<table class='quote-running-header' width='100%' cellspacing='0' cellpadding='0'>"
        "<tr>"
        "<td width='68%' align='left' valign='middle'>"
        "<span style='font-size:11px;font-weight:700;color:#111827;'>PIANO ACADEMIE</span>"
        "</td>"
        "<td width='32%' align='right' valign='middle' style='font-size:10px;color:#334155;'>"
        f"<strong>{escape(_quote_doc_text('cover_quote', language=language))} {escape(quote.quote_number or '-')}</strong>"
        "</td>"
        "</tr>"
        "</table>"
    )
    cover_page_standard_html = (
        "<section class='quote-cover'>"
        f"{cover_logo_html}"
        f"<h1 class='quote-cover-title'>{escape(_quote_doc_text('cover_title', language=language))}</h1>"
        f"<p class='quote-cover-subtitle'>{escape(_quote_doc_text('cover_school_year', language=language))} {escape(quote.school_year_label or '-')}</p>"
        f"<p class='quote-cover-name'>{escape(prospect_data.get('child_full_name') or recipient_name)}</p>"
        "<div class='quote-cover-meta'>"
        f"<p>{escape(_quote_doc_text('prospect_type', language=language))}: {escape(_quote_doc_text('prospect_type_child' if str(prospect_data.get('prospect_type') or '').lower() == 'child' else 'prospect_type_adult', language=language))}</p>"
        f"<p>{escape(_quote_doc_text('generated_at', language=language))} {escape(_datetime_label(_utcnow()))}</p>"
        f"<p>{escape(quote_status_cover_line)}</p>"
        "</div>"
        "</section>"
        "<div class='quote-page-break'></div>"
    )

    values: dict[str, str] = {
        "cover_title": _quote_doc_text("cover_title", language=language),
        "cover_quote": _quote_doc_text("cover_quote", language=language),
        "cover_school_year": _quote_doc_text("cover_school_year", language=language),
        "cover_student": _quote_doc_text("cover_student", language=language),
        "quote_recipient": _quote_doc_text("quote_recipient", language=language),
        "identity_title": _quote_doc_text("identity_title", language=language),
        "section_courses_options": _quote_doc_text("section_courses_options", language=language),
        "payment_title": _quote_doc_text("payment_title", language=language),
        "calendar_title": _quote_doc_text("calendar_title", language=language),
        "calendar_overview_label": _quote_doc_text("calendar_overview", language=language, summary="").split(":", 1)[0].strip(),
        "terms_title": _quote_doc_text("terms_title", language=language),
        "quote_number": quote.quote_number or "-",
        "recipient_name": recipient_name,
        "recipient_email": recipient_email,
        "total_ttc": _decimal_str(total_ttc),
        "total_ttc_before_adjustment": _decimal_str(total_before_adjustment),
        "total_ttc_after_adjustment": _decimal_str(total_after_adjustment),
        "total_ht": _decimal_str(total_ht_after_adjustment),
        "total_ht_before_adjustment": _decimal_str(total_ht_before_adjustment),
        "total_ht_after_adjustment": _decimal_str(total_ht_after_adjustment),
        "vat_rate": _decimal_str(vat_rate),
        "vat_amount": _decimal_str(vat_amount_after_adjustment),
        "vat_amount_before_adjustment": _decimal_str(vat_amount_before_adjustment),
        "vat_amount_after_adjustment": _decimal_str(vat_amount_after_adjustment),
        "currency": currency,
        "expires_at": _date_label(display_quote_expires_at(quote)),
        "sent_at": _datetime_label(quote.sent_at),
        "generated_at": _datetime_label(_utcnow()),
        "school_year_label": (quote.school_year_label or "-"),
        "quote_status_date_label": quote_status_date_label,
        "quote_status_date_value": quote_status_date_value,
        "calendar_summary": calendar_summary,
        "payment_schedule_summary": payment_schedule_summary,
        "financial_adjustment_type": adjustment_type,
        "financial_adjustment_type_label": adjustment_type_label,
        "financial_adjustment_amount_ttc": _decimal_str(adjustment_amount),
        "financial_adjustment_signed_amount_ttc": _decimal_str(adjustment_signed_amount),
        "financial_adjustment_effective_date": adjustment_effective_date,
        "financial_adjustment_label": adjustment_label,
        "financial_adjustment_display_title": adjustment_display_title if has_financial_adjustment else "",
        "financial_adjustment_display_line": adjustment_display_line,
        "financial_adjustment_impact_label": adjustment_impact_label,
        "has_financial_adjustment": "true" if has_financial_adjustment else "false",
        "has_credit_adjustment": "true" if has_credit_adjustment else "false",
        "has_debt_adjustment": "true" if has_debt_adjustment else "false",
        "financial_adjustment_block_html": financial_adjustment_block_html,
        "financial_adjustment_section_html": financial_adjustment_section_html,
        "financial_adjustment_none_html": financial_adjustment_none_html,
        "financial_recap_block_html": financial_recap_block_html,
        "total_ttc_before_adjustment_html": total_ttc_before_adjustment_html,
        "total_before_adjustment": _decimal_str(total_before_adjustment),
        "total_after_adjustment": _decimal_str(total_after_adjustment),
        "has_deposit": "true" if has_deposit else "false",
        "deposit_enabled": "true" if has_deposit else "false",
        "deposit_amount_ttc": _decimal_str(deposit_amount_ttc),
        "deposit_ht_amount": _decimal_str(deposit_ht_amount),
        "deposit_vat_amount": _decimal_str(deposit_vat_amount),
        "remaining_ttc_after_deposit": _decimal_str(remaining_ttc_after_deposit),
        "remaining_ht_after_deposit": _decimal_str(remaining_ht_after_deposit),
        "remaining_vat_after_deposit": _decimal_str(remaining_vat_after_deposit),
        "deposit_block_html": deposit_block_html,
        "deposit_section_html": deposit_section_html,
        "deposit_none_html": deposit_none_html,
        "payment_method": str(document_context.get("payment_method") or "").strip(),
        "payment_method_label": payment_method_label,
        "payment_instruction": payment_instruction,
        "payment_schedule_compact_notice": document_context["payment_schedule_compact_notice"] or "",
        "document_style_html": _document_style_html(),
        "brand_logo_html": brand_logo_html,
        "header_standard_html": header_standard_html,
        "cover_page_standard_html": cover_page_standard_html,
        "page_break_html": "<div class='quote-page-break'></div>",
        "footer_standard_html": (
            "<table class='quote-running-footer' width='100%' cellspacing='0' cellpadding='0'>"
            "<tr>"
            "<td width='33%' align='left' valign='top'>"
            "Piano Academie<br/>"
            "1 rue de Richelieu<br/>"
            "75001 Paris"
            "</td>"
            "<td width='34%' align='center' valign='top'>"
            "SIRET 82805141700032<br/>"
            "FR 74828051417"
            "</td>"
            f"<td width='33%' align='right' valign='top'>{escape(quote.quote_number or '-')}</td>"
            "</tr>"
            "</table>"
        ),
        "cgv_version": cgv_label or _quote_doc_text("terms_version_unspecified", language=language),
        "services_count": str(len(services)),
        "products_count": str(len(products)),
        "kits_count": str(len(kits)),
        "adjustments_count": str(len(adjustments)),
        "other_fees_count": str(len(other_fees)),
        "lines_count": str(len(lines)),
        "prospect_identity_block_html": prospect_identity_block_html,
        "solfege_block_html": solfege_block_html,
        "masterclass_block_html": masterclass_block_html,
        "end_year_concert_block_html": end_year_concert_block_html,
        "end_year_concert_compact_notice_html": end_year_concert_compact_notice_html,
        "end_year_concert_compact_notice_pdf_html": end_year_concert_compact_notice_pdf_html,
        "pass_recup_block_html": pass_recup_block_html,
        "pass_recup_compact_notice_html": pass_recup_compact_notice_html,
        "pass_recup_compact_notice_pdf_html": pass_recup_compact_notice_pdf_html,
        "options_section_html": options_section_html,
        "payment_method_block_html": payment_method_block_html,
        "activities_planning_section_html": activities_planning_section_html,
        "services_section_html": services_section_html,
        "adjustments_section_html": adjustments_section_html,
        "products_section_html": products_section_html,
        "kits_section_html": kits_section_html,
        "other_fees_section_html": other_fees_section_html,
        "payment_schedule_section_html": payment_schedule_section_html,
        "calendar_section_html": calendar_section_html,
        "services_table_html": services_table_html,
        "activities_planning_table_html": planning_blocks_table_html,
        "products_table_html": products_table_html,
        "kits_table_html": kits_table_html,
        "adjustments_table_html": adjustments_table_html,
        "other_fees_table_html": other_fees_table_html,
        "lines_table_html": lines_table_html,
        "payment_schedule_table_html": payment_schedule_table_html,
        "calendar_table_html": calendar_table_html,
        "calendar_activity_semesters_html": calendar_table_html,
        "calendar_sessions_table_html": calendar_sessions_table_html,
        "show_adult_block": "true" if display_flags["showAdultBlock"] else "false",
        "show_child_block": "true" if display_flags["showChildBlock"] else "false",
        "show_solfege_section": "true" if display_flags["showSolfegeSection"] else "false",
        "show_masterclass_section": "true" if display_flags["showMasterclassSection"] else "false",
        "show_end_year_concert_section": "true" if display_flags["showEndYearConcertSection"] else "false",
        "show_pass_recup_section": "true" if display_flags["showPassRecupSection"] else "false",
        "show_payment_schedule_detailed": "true" if display_flags["showPaymentScheduleDetailed"] else "false",
    }
    values.update(prospect_data)
    values["prospect_type_label"] = _quote_doc_text(
        "prospect_type_child" if str(prospect_data.get("prospect_type") or "").lower() == "child" else "prospect_type_adult",
        language=language,
    )
    values.update(client_data)

    html_keys = {
        "prospect_identity_block_html",
        "solfege_block_html",
        "masterclass_block_html",
        "end_year_concert_block_html",
        "end_year_concert_compact_notice_html",
        "pass_recup_block_html",
        "pass_recup_compact_notice_html",
        "options_section_html",
        "payment_method_block_html",
        "activities_planning_section_html",
        "services_section_html",
        "adjustments_section_html",
        "products_section_html",
        "kits_section_html",
        "other_fees_section_html",
        "payment_schedule_section_html",
        "calendar_section_html",
        "financial_adjustment_block_html",
        "financial_adjustment_section_html",
        "financial_adjustment_none_html",
        "financial_recap_block_html",
        "deposit_block_html",
        "deposit_section_html",
        "deposit_none_html",
        "total_ttc_before_adjustment_html",
        "services_table_html",
        "activities_planning_table_html",
        "products_table_html",
        "kits_table_html",
        "adjustments_table_html",
        "other_fees_table_html",
        "lines_table_html",
        "payment_schedule_table_html",
        "calendar_table_html",
        "calendar_activity_semesters_html",
        "calendar_sessions_table_html",
        "document_style_html",
        "brand_logo_html",
        "header_standard_html",
        "cover_page_standard_html",
        "page_break_html",
        "footer_standard_html",
    }
    return values, html_keys, document_context


def build_quote_template_values(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> tuple[dict[str, str], set[str], dict[str, Any]]:
    values, html_keys, document_context = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    return dict(values), set(html_keys), dict(document_context)


def _default_quote_body_template() -> str:
    return (
        "{document_style_html}"
        "{cover_page_standard_html}"
        "{header_standard_html}"
        "<h1>{cover_quote} {quote_number}</h1>"
        "<p><strong>{quote_recipient}:</strong> {recipient_name}</p>"
        "<p><strong>{cover_school_year}:</strong> {school_year_label}</p>"
        "<p><strong>{quote_status_date_label}:</strong> {quote_status_date_value}</p>"
        "{page_break_html}"
        "<h2>{identity_title}</h2>"
        "<div class='quote-block'>"
        "{prospect_identity_block_html}"
        "</div>"
        "{activities_planning_section_html}"
        "{services_section_html}"
        "{adjustments_section_html}"
        "{products_section_html}"
        "{kits_section_html}"
        "{other_fees_section_html}"
        "{deposit_section_html}"
        "{financial_recap_block_html}"
        "<h2>{payment_title}</h2>"
        "{payment_method_block_html}"
        "<p>{payment_schedule_summary}</p>"
        "{payment_schedule_table_html}"
        "{financial_adjustment_section_html}"
        "{options_section_html}"
        "<h2>{calendar_title}</h2>"
        "<p><strong>{calendar_overview_label} :</strong> {calendar_summary}</p>"
        "{calendar_activity_semesters_html}"
        "{footer_standard_html}"
    )


def _render_quote_body_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    _, body_template = _load_quote_template_snapshot(db=db, quote=quote)
    template = _normalize_template_source(body_template or _default_quote_body_template())
    template = _strip_legacy_recipient_email_markup(template)
    lowered_template = template.lower()
    if "{deposit_section_html}" not in lowered_template and "{deposit_block_html}" not in lowered_template:
        if "{payment_method_block_html}" in lowered_template:
            template = template.replace("{payment_method_block_html}", "{deposit_section_html}{payment_method_block_html}", 1)
        else:
            template += "{deposit_section_html}"
    if "{other_fees_section_html}" not in lowered_template and "{other_fees_table_html}" not in lowered_template:
        if "{kits_section_html}" in lowered_template:
            template = template.replace("{kits_section_html}", "{kits_section_html}{other_fees_section_html}", 1)
        elif "{kits_table_html}" in lowered_template:
            template = template.replace("{kits_table_html}", "{kits_table_html}{other_fees_section_html}", 1)
        else:
            template += "{other_fees_section_html}"
    if "{financial_recap_block_html}" not in template:
        legacy_financial_tokens = (
            "{total_ttc_before_adjustment_html}",
            "{total_ht_before_adjustment}",
            "{vat_amount_before_adjustment}",
            "{total_ht_after_adjustment}",
            "{vat_amount_after_adjustment}",
            "{total_ttc_after_adjustment}",
            "{total_ht}",
            "{vat_amount}",
            "{total_after_adjustment}",
            "{total_ttc}",
        )
        if any(token in template for token in legacy_financial_tokens):
            template = re.sub(
                r"<p[^>]*>\s*<strong>\s*"
                r"(?:Total(?:\s+TTC(?:\s+avant\s+ajustement|\s+facture)?|\s+HT(?:\s+avant\s+ajustement)?|"
                r"\s+avant\s+ajustement)|TVA(?:\s*\([^)]+\))?(?:\s+avant\s+ajustement|\s+facture)?)"
                r"\s*:?\s*</strong>.*?</p>",
                "",
                template,
                flags=re.IGNORECASE | re.DOTALL,
            )
            template += "{financial_recap_block_html}"
    template = _normalize_block_placeholder_wrappers(
        template,
        keys={
            "document_style_html",
            "brand_logo_html",
            "header_standard_html",
            "cover_page_standard_html",
            "page_break_html",
            "footer_standard_html",
            "prospect_identity_block_html",
            "solfege_block_html",
            "masterclass_block_html",
            "end_year_concert_block_html",
            "end_year_concert_compact_notice_html",
            "pass_recup_block_html",
            "options_section_html",
            "payment_method_block_html",
            "activities_planning_section_html",
            "services_section_html",
            "adjustments_section_html",
            "products_section_html",
            "kits_section_html",
            "other_fees_section_html",
            "payment_schedule_section_html",
            "calendar_section_html",
            "services_table_html",
            "activities_planning_table_html",
            "products_table_html",
            "kits_table_html",
            "adjustments_table_html",
            "other_fees_table_html",
            "lines_table_html",
            "payment_schedule_table_html",
            "calendar_table_html",
            "calendar_activity_semesters_html",
            "calendar_sessions_table_html",
            "financial_adjustment_block_html",
            "financial_adjustment_section_html",
            "financial_adjustment_none_html",
            "financial_recap_block_html",
            "deposit_block_html",
            "deposit_section_html",
            "deposit_none_html",
        },
    )
    values, html_keys, _ = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    rendered = _apply_template(template, values=values, html_keys=html_keys, html_output=True)
    rendered = _cleanup_rendered_block_markup(rendered)
    rendered = _dedupe_retained_activities_tables(rendered)
    if not str(values.get("adjustments_section_html") or "").strip():
        rendered = re.sub(
            r"<h[1-6]\b[^>]*>\s*Remises\s+et\s+suppl(?:e|é)ments\s*</h[1-6]>\s*",
            "",
            rendered,
            flags=re.IGNORECASE,
        )
    if not str(values.get("options_section_html") or "").strip():
        rendered = re.sub(
            r"<h[1-6]\b[^>]*>\s*(?:Vos\s+options|Your\s+options)\s*</h[1-6]>\s*",
            "",
            rendered,
            flags=re.IGNORECASE,
        )
    lowered_template = template.lower()
    if "{activities_planning_table_html}" not in lowered_template and "{activities_planning_section_html}" not in lowered_template:
        rendered += values.get("activities_planning_section_html", "")
    rendered = _replace_expiration_mentions_for_approved_quote(rendered, quote)
    rendered = _enforce_family_page_break(rendered)
    return _as_html_fragment(rendered)


def _render_quote_terms_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    language = _quote_doc_language(quote=quote)
    cgv_label, cgv_content = _load_terms_template_content(db=db, quote=quote)
    cgv_label = _localized_english_text_fragments(cgv_label, language=language)
    cgv_content = _localized_english_text_fragments(cgv_content, language=language)
    values, html_keys, _ = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    rendered_terms = _render_terms_content_html(content=cgv_content, values=values, html_keys=html_keys)
    header_html = values.get("header_standard_html", "")
    footer_html = values.get("footer_standard_html", "")
    return (
        "<section>"
        f"{header_html}"
        f"<h2 class='quote-terms-title'>{escape(_quote_doc_text('terms_title', language=language))}</h2>"
        "<div class='quote-block'>"
        f"<p><strong>{escape(cgv_label or _quote_doc_text('terms_version_unspecified', language=language))}</strong></p>"
        f"{_as_html_fragment(rendered_terms or _quote_doc_text('terms_snapshot_empty', language=language))}"
        "</div>"
        f"{footer_html}"
        "</section>"
    )


def render_quote_combined_html(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    language = _quote_doc_language(quote=quote)
    body_html = _localized_english_text_fragments(
        _render_quote_body_html(db=db, quote=quote, lines=lines, audience=audience),
        language=language,
    )
    terms_html = _localized_english_text_fragments(
        _render_quote_terms_html(db=db, quote=quote, lines=lines, audience=audience),
        language=language,
    )
    base_css = _document_style_html()
    return (
        "<html><head><meta charset='utf-8'/>"
        f"{base_css}"
        "</head><body style='font-family:Arial,sans-serif;color:#1a1a1a;'>"
        f"{base_css}"
        f"<section>{body_html}</section>"
        "<div class='quote-page-break'></div>"
        f"{terms_html}"
        "</body></html>"
    )


def render_quote_html(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    return render_quote_combined_html(db=db, quote=quote, lines=lines, audience=audience)


def render_quote_parts_html(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> tuple[str, str, str]:
    language = _quote_doc_language(quote=quote)
    body_html = _localized_english_text_fragments(
        _render_quote_body_html(db=db, quote=quote, lines=lines, audience=audience),
        language=language,
    )
    terms_html = _localized_english_text_fragments(
        _render_quote_terms_html(db=db, quote=quote, lines=lines, audience=audience),
        language=language,
    )
    base_css = _document_style_html()
    combined_html = (
        "<html><head><meta charset='utf-8'/>"
        f"{base_css}"
        "</head><body style='font-family:Arial,sans-serif;color:#1a1a1a;'>"
        f"{base_css}"
        f"<section>{body_html}</section>"
        "<div class='quote-page-break'></div>"
        f"{terms_html}"
        "</body></html>"
    )
    return body_html, terms_html, combined_html


def render_quote_document_bundle(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> dict[str, Any]:
    values, _, context = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    body_html, terms_html, combined_html = render_quote_parts_html(db=db, quote=quote, lines=lines, audience=audience)
    return {
        "audience": audience,
        "quote_id": str(quote.id),
        "quote_number": quote.quote_number,
        "body_html": body_html,
        "terms_html": terms_html,
        "combined_html": combined_html,
        "display_flags": context.get("display_flags", {}),
        "visible_blocks": context.get("visible_blocks", []),
        "hidden_blocks": context.get("hidden_blocks", []),
        "payment_method_label": values.get("payment_method_label", ""),
        "payment_schedule_compact_notice": values.get("payment_schedule_compact_notice", ""),
    }


def render_quote_pdf(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> bytes:
    _, _, combined_html = render_quote_parts_html(db=db, quote=quote, lines=lines, audience=audience)
    return render_quote_pdf_from_combined_html(
        db=db,
        quote=quote,
        lines=lines,
        combined_html=combined_html,
        audience=audience,
    )


def _safe_logo_reader(data_url: str) -> ImageReader | None:
    raw = str(data_url or "").strip()
    if not raw.startswith("data:image/") or "," not in raw:
        return None
    payload = raw.split(",", 1)[1]
    try:
        content = base64.b64decode(payload, validate=False)
    except Exception:
        return None
    try:
        return ImageReader(io.BytesIO(content))
    except Exception:
        return None


def _quote_pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=8,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#475467"),
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=2,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=4,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#111827"),
            spaceBefore=2,
            spaceAfter=5,
        ),
        "text": ParagraphStyle(
            "text",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=5,
        ),
        "text_center": ParagraphStyle(
            "text_center",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=5,
        ),
        "small_muted": ParagraphStyle(
            "small_muted",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#667085"),
            spaceAfter=4,
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=12.5,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_LEFT,
            wordWrap="LTR",
            splitLongWords=False,
            spaceAfter=0,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor("#111827"),
            alignment=TA_LEFT,
            wordWrap="LTR",
            splitLongWords=False,
            spaceAfter=0,
        ),
    }


def _table_for_pdf(
    headers: list[str],
    rows: list[list[Any]],
    *,
    width: float,
    styles: dict[str, ParagraphStyle],
    col_widths: list[float] | None = None,
) -> Table:
    def _as_cell(value: Any, style: ParagraphStyle) -> Paragraph:
        if isinstance(value, Paragraph):
            return value
        if isinstance(value, dict):
            raw_html = value.get("html")
            if raw_html is not None:
                return Paragraph(str(raw_html), style)
            text = escape(str(value.get("text") or "")).replace("\n", "<br/>")
            subtext = str(value.get("subtext") or "").strip()
            if subtext:
                text += (
                    "<br/><font size='9' color='#64748b'>"
                    + escape(subtext).replace("\n", "<br/>")
                    + "</font>"
                )
            return Paragraph(text or "-", style)
        text = str(value if value is not None else "-")
        text = escape(text).replace("\n", "<br/>")
        return Paragraph(text, style)

    normalized_rows = rows if rows else [["-"] * max(1, len(headers))]
    data: list[list[Any]] = [
        [_as_cell(cell, styles["table_header"]) for cell in headers],
        *[[_as_cell(cell, styles["table_cell"]) for cell in row] for row in normalized_rows],
    ]
    col_count = len(headers) if headers else 1
    if col_widths and len(col_widths) == col_count:
        total_ratio = sum(max(0.0, float(value)) for value in col_widths)
        if total_ratio > 0:
            final_widths = [width * (max(0.0, float(value)) / total_ratio) for value in col_widths]
        else:
            col_width = width / col_count
            final_widths = [col_width] * col_count
    else:
        col_width = width / col_count
        final_widths = [col_width] * col_count
    table = Table(data, colWidths=final_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EDF7")),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.9, colors.HexColor("#c4cfde")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _terms_lines_for_pdf(content: str, *, values: dict[str, str], language: str | None = None) -> list[str]:
    normalized = _normalize_template_source(content or "")
    if not normalized:
        return [_quote_doc_text("terms_empty", language=language)]
    substituted = _apply_template(normalized, values=values, html_keys=set(), html_output=False)
    raw = str(substituted or "")
    raw = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)<li\b[^>]*>", "• ", raw)
    raw = re.sub(r"(?i)</(p|div|section|h[1-6]|li|tr|table|ul|ol)>", "\n", raw)
    raw = re.sub(r"(?i)</(td|th)>", "  ", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_unescape(raw)
    raw = raw.replace("\r", "")
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    return lines or [_quote_doc_text("terms_empty", language=language)]


_TERMS_RENDER_BLOCK_KEYS = {
    "document_style_html",
    "brand_logo_html",
    "header_standard_html",
    "cover_page_standard_html",
    "page_break_html",
    "footer_standard_html",
    "prospect_identity_block_html",
    "solfege_block_html",
    "masterclass_block_html",
    "end_year_concert_block_html",
    "end_year_concert_compact_notice_html",
    "pass_recup_block_html",
    "pass_recup_compact_notice_html",
    "options_section_html",
    "payment_method_block_html",
    "activities_planning_section_html",
    "services_section_html",
    "adjustments_section_html",
    "products_section_html",
    "kits_section_html",
    "other_fees_section_html",
    "payment_schedule_section_html",
    "calendar_section_html",
    "payment_schedule_table_html",
    "calendar_table_html",
    "calendar_activity_semesters_html",
    "financial_recap_block_html",
    "deposit_block_html",
    "deposit_section_html",
    "deposit_none_html",
    "other_fees_table_html",
}


def _render_terms_content_html(*, content: str, values: dict[str, str], html_keys: set[str]) -> str:
    normalized_terms = _normalize_template_source(content or "")
    normalized_terms = _strip_legacy_recipient_email_markup(normalized_terms)
    normalized_terms = _normalize_block_placeholder_wrappers(
        normalized_terms,
        keys=_TERMS_RENDER_BLOCK_KEYS,
    )
    rendered_terms = _apply_template(normalized_terms, values=values, html_keys=html_keys, html_output=True)
    rendered_terms = _cleanup_rendered_block_markup(rendered_terms)
    rendered_terms = _normalize_template_source(rendered_terms)
    return _cleanup_legacy_terms_layout(rendered_terms)


def _reportlab_font_size(value: str) -> str | None:
    raw = str(value or "").strip().lower()
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(px|pt)?", raw)
    if match is None:
        return None
    amount = float(match.group(1))
    unit = match.group(2) or "pt"
    if unit == "px":
        amount *= 0.75
    if amount <= 0:
        return None
    rounded = round(amount, 1)
    return str(int(rounded)) if float(rounded).is_integer() else str(rounded)


def _reportlab_font_face(*, family: str, bold: bool, italic: bool) -> str | None:
    raw = str(family or "").strip().strip("'\"")
    if not raw:
        return None
    normalized = raw.casefold()
    base = "Helvetica"
    if any(token in normalized for token in ("courier", "mono", "menlo", "monaco", "consolas")):
        base = "Courier"
    elif any(token in normalized for token in ("times", "georgia", "serif")):
        base = "Times"
    if base == "Helvetica":
        if bold and italic:
            return "Helvetica-BoldOblique"
        if bold:
            return "Helvetica-Bold"
        if italic:
            return "Helvetica-Oblique"
        return "Helvetica"
    if base == "Times":
        if bold and italic:
            return "Times-BoldItalic"
        if bold:
            return "Times-Bold"
        if italic:
            return "Times-Italic"
        return "Times-Roman"
    if bold and italic:
        return "Courier-BoldOblique"
    if bold:
        return "Courier-Bold"
    if italic:
        return "Courier-Oblique"
    return "Courier"


def _inline_style_map(style_value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in str(style_value or "").split(";"):
        if ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip()
        if normalized_key and normalized_value:
            out[normalized_key] = normalized_value
    return out


def _reportlab_markup_from_attrs(tag: str, attrs: dict[str, str]) -> tuple[str, str]:
    style_map = _inline_style_map(attrs.get("style", ""))
    bold = False
    weight = style_map.get("font-weight", "").strip().lower()
    if weight == "bold":
        bold = True
    elif weight.isdigit():
        bold = int(weight) >= 600
    italic = "italic" in style_map.get("font-style", "").strip().lower()
    underline = "underline" in style_map.get("text-decoration", "").strip().lower()
    family = attrs.get("face") or style_map.get("font-family", "")
    size = attrs.get("size") or style_map.get("font-size", "")
    color = attrs.get("color") or style_map.get("color", "")

    font_attrs: list[str] = []
    face = _reportlab_font_face(family=family, bold=bold, italic=italic) if family else None
    if face:
        font_attrs.append(f"face='{escape(face)}'")
        bold = False
        italic = False
    parsed_size = _reportlab_font_size(size) if size else None
    if parsed_size:
        font_attrs.append(f"size='{escape(parsed_size)}'")
    normalized_color = str(color or "").strip()
    if normalized_color and re.fullmatch(r"#[0-9a-fA-F]{3,8}|[a-zA-Z]+", normalized_color):
        font_attrs.append(f"color='{escape(normalized_color)}'")

    open_parts: list[str] = []
    close_parts: list[str] = []
    if font_attrs:
        open_parts.append(f"<font {' '.join(font_attrs)}>")
        close_parts.insert(0, "</font>")
    if bold:
        open_parts.append("<b>")
        close_parts.insert(0, "</b>")
    if italic:
        open_parts.append("<i>")
        close_parts.insert(0, "</i>")
    if underline:
        open_parts.append("<u>")
        close_parts.insert(0, "</u>")
    return "".join(open_parts), "".join(close_parts)


class _ReportLabTermsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self._current: list[str] = []
        self._current_style = "text"
        self._open_tags: list[tuple[str, str]] = []
        self._ignored_depth = 0
        self._list_item_depth = 0

    def _begin_block(self, style: str) -> None:
        self._flush_block()
        self._current_style = style

    def _append(self, markup: str) -> None:
        if markup:
            self._current.append(markup)

    def _current_markup(self) -> str:
        return "".join(self._current).strip()

    def _close_tag(self, tag: str) -> None:
        if self._open_tags and self._open_tags[-1][0] == tag:
            _, closer = self._open_tags.pop()
            self._append(closer)

    def _flush_block(self) -> None:
        while self._open_tags:
            _, closer = self._open_tags.pop()
            self._append(closer)
        markup = "".join(self._current).strip()
        markup = re.sub(r"(?:<br\s*/?>\s*){3,}", "<br/><br/>", markup, flags=re.IGNORECASE)
        if markup:
            self.blocks.append((self._current_style, markup))
        self._current = []
        self._current_style = "text"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"style", "script"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        attrs_dict = {str(key or "").lower(): str(value or "") for key, value in attrs}
        if normalized_tag == "li":
            self._begin_block("text")
            self._list_item_depth += 1
            self._append("• ")
            return
        if normalized_tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "tr"}:
            if self._list_item_depth > 0:
                current = self._current_markup()
                if current and current != "•" and current != "• " and not current.endswith("<br/>"):
                    self._append("<br/>")
                return
            style = "h1" if normalized_tag == "h1" else "h2" if normalized_tag == "h2" else "h3" if normalized_tag.startswith("h") else "text"
            self._begin_block(style)
            return
        if normalized_tag == "br":
            self._append("<br/>")
            return
        if normalized_tag in {"strong", "b"}:
            self._append("<b>")
            self._open_tags.append((normalized_tag, "</b>"))
            return
        if normalized_tag in {"em", "i"}:
            self._append("<i>")
            self._open_tags.append((normalized_tag, "</i>"))
            return
        if normalized_tag == "u":
            self._append("<u>")
            self._open_tags.append((normalized_tag, "</u>"))
            return
        if normalized_tag == "th":
            if not self._current:
                self._begin_block("text")
            self._append("<b>")
            self._open_tags.append((normalized_tag, "</b>"))
            return
        if normalized_tag in {"td", "span", "font"}:
            if not self._current and normalized_tag == "td":
                self._begin_block("text")
            open_markup, close_markup = _reportlab_markup_from_attrs(normalized_tag, attrs_dict)
            self._append(open_markup)
            if close_markup:
                self._open_tags.append((normalized_tag, close_markup))

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"style", "script"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if normalized_tag in {"strong", "b", "em", "i", "u", "span", "font", "th"}:
            self._close_tag(normalized_tag)
            return
        if normalized_tag == "td":
            self._append("  ")
            return
        if normalized_tag == "li":
            if self._list_item_depth > 0:
                self._list_item_depth -= 1
            self._flush_block()
            return
        if normalized_tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "tr"}:
            if self._list_item_depth > 0:
                return
            self._flush_block()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = str(data or "")
        if not text.strip():
            if self._current and ("\n" in text or "\r" in text):
                self._append(" ")
            return
        if not self._current:
            self._begin_block("text")
        self._append(escape(text))

    def close(self) -> None:
        super().close()
        self._flush_block()


def _terms_flowables_for_pdf(
    content: str,
    *,
    values: dict[str, str],
    html_keys: set[str],
    styles: dict[str, ParagraphStyle],
    language: str | None = None,
) -> list[Paragraph]:
    rendered_terms = _render_terms_content_html(content=content, values=values, html_keys=html_keys)
    if not rendered_terms:
        return [Paragraph(escape(_quote_doc_text("terms_empty", language=language)), styles["text"])]
    parser = _ReportLabTermsParser()
    parser.feed(rendered_terms)
    parser.close()
    blocks = parser.blocks or [("text", escape(_quote_doc_text("terms_empty", language=language)))]
    return [Paragraph(markup, styles.get(style_name, styles["text"])) for style_name, markup in blocks]


def _draw_quote_pdf_header_footer(
    canvas_obj: Any,
    doc: SimpleDocTemplate,
    *,
    quote_number: str,
    quote_label: str,
    logo_reader: ImageReader | None,
) -> None:
    canvas_obj.saveState()
    page_width, page_height = A4
    left_x = doc.leftMargin
    right_x = page_width - doc.rightMargin

    # Header band: center visual elements vertically between top band and separator line.
    header_band_top = page_height - 10 * mm
    header_rule_y = page_height - 24 * mm
    header_band_center_y = (header_band_top + header_rule_y) / 2

    logo_width = 28 * mm
    logo_height = 10 * mm
    logo_y = header_band_center_y - (logo_height / 2)
    if logo_reader is not None:
        try:
            canvas_obj.drawImage(
                logo_reader,
                left_x,
                logo_y,
                width=logo_width,
                height=logo_height,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            logo_reader = None

    title_baseline_y = header_band_center_y - (3.2 * mm)
    canvas_obj.setFont("Helvetica-Bold", 11)
    canvas_obj.setFillColor(colors.HexColor("#0f172a"))
    if logo_reader is None:
        canvas_obj.drawString(left_x, title_baseline_y, "PIANO ACADEMIE")
    canvas_obj.drawRightString(right_x, title_baseline_y, f"{quote_label} {quote_number or '-'}")
    canvas_obj.setStrokeColor(colors.HexColor("#cfd8e6"))
    canvas_obj.setLineWidth(0.8)
    canvas_obj.line(left_x, header_rule_y, right_x, header_rule_y)

    footer_y = 15 * mm
    canvas_obj.setStrokeColor(colors.HexColor("#cfd8e6"))
    canvas_obj.setLineWidth(0.8)
    canvas_obj.line(left_x, footer_y + 11 * mm, right_x, footer_y + 11 * mm)
    canvas_obj.setFont("Helvetica", 9.5)
    canvas_obj.setFillColor(colors.HexColor("#334155"))
    canvas_obj.drawString(left_x, footer_y + 6 * mm, "Piano Academie")
    canvas_obj.drawString(left_x, footer_y + 2 * mm, "1 rue de Richelieu")
    canvas_obj.drawString(left_x, footer_y - 2 * mm, "75001 Paris")
    canvas_obj.drawCentredString((left_x + right_x) / 2, footer_y + 6 * mm, "SIRET 82805141700032")
    canvas_obj.drawCentredString((left_x + right_x) / 2, footer_y + 2 * mm, "FR 74828051417")
    canvas_obj.drawRightString(right_x, footer_y + 6 * mm, quote_number or "-")
    canvas_obj.restoreState()


def _render_quote_pdf_blocks(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str,
) -> bytes:
    language = _quote_doc_language(quote=quote)
    values, html_keys, context = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    prospect_data = context.get("prospect_data", {})
    calendar_snapshot = _json_object(context.get("calendar_snapshot")) or _calendar_snapshot_with_planning_sessions(db, _json_object(quote.calendar_snapshot))
    sessions = [item for item in _json_list(calendar_snapshot.get("sessions")) if isinstance(item, dict)]
    planning_blocks = [item for item in _json_list(calendar_snapshot.get("blocks")) if isinstance(item, dict)]
    selected_solfege_slot = _json_object(context.get("solfege_selected_slot"))
    service_product_ids = _service_product_ids_for_lines(db=db, lines=lines)
    services, products, kits, adjustments, other_fees = _line_groups(lines, service_product_ids=service_product_ids)
    product_long_descriptions = _product_long_descriptions_by_id(db=db, products=products)
    kit_long_descriptions = _kit_long_descriptions_by_id(db=db, kits=kits)
    kit_composition = _kit_composition_by_id(db=db, kits=kits, language=language)
    schedule = [item for item in _json_list(context.get("schedule")) if isinstance(item, dict)]
    styles = _quote_pdf_styles()
    cgv_label, cgv_content = _load_terms_template_content(db=db, quote=quote)
    cgv_label = _localized_english_text_fragments(cgv_label, language=language)
    cgv_content = _localized_english_text_fragments(cgv_content, language=language)
    terms_flowables = _terms_flowables_for_pdf(cgv_content, values=values, html_keys=html_keys, styles=styles, language=language)
    logo_reader = _safe_logo_reader(_account_logo_data_url(db=db))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=30 * mm,
        bottomMargin=24 * mm,
        title=f"{_quote_doc_text('cover_quote', language=language)} {quote.quote_number or '-'}",
        author="Piano Academie",
    )
    content_width = A4[0] - doc.leftMargin - doc.rightMargin
    story: list[Any] = []

    story.append(Spacer(1, 18 * mm))
    story.append(Paragraph(_quote_doc_text("cover_title", language=language), styles["cover_title"]))
    story.append(Paragraph(f"{_quote_doc_text('cover_quote', language=language)} : {escape(values.get('quote_number', '-'))}", styles["cover_subtitle"]))
    story.append(Paragraph(f"{_quote_doc_text('cover_school_year', language=language)} : {escape(values.get('school_year_label', '-'))}", styles["cover_subtitle"]))
    story.append(
        Paragraph(
            f"{escape(values.get('quote_status_date_label', _quote_doc_text('quote_status_validity', language=language)))} : {escape(values.get('quote_status_date_value', values.get('expires_at', '-')))}",
            styles["cover_subtitle"],
        )
    )
    story.append(
        Paragraph(
            f"{_quote_doc_text('cover_student', language=language)} : {escape(prospect_data.get('child_full_name') or values.get('recipient_name', '-'))}",
            styles["cover_subtitle"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph(_quote_doc_text("identity_title", language=language), styles["h1"]))
    identity_rows: list[list[str]] = []
    if str(prospect_data.get("prospect_type") or "").lower() == "child":
        identity_rows.extend(
            [
                [_quote_doc_text("identity_child", language=language), str(prospect_data.get("child_full_name") or "-")],
                [_quote_doc_text("identity_birth_date", language=language), _birth_date_label(str(prospect_data.get("child_birth_date") or ""))],
                [_quote_doc_text("identity_adult_contact", language=language), str(prospect_data.get("parent_full_name") or "-")],
                [_quote_doc_text("identity_adult_contact_email", language=language), str(prospect_data.get("parent_email") or values.get("recipient_email") or "-")],
                [_quote_doc_text("identity_adult_contact_phone", language=language), str(prospect_data.get("parent_phone") or "-")],
                [_quote_doc_text("identity_adult_contact_address", language=language), str(prospect_data.get("parent_address") or "-")],
            ]
        )
    else:
        identity_rows.extend(
            [
                [_quote_doc_text("identity_adult_contact", language=language), str(prospect_data.get("adult_full_name") or values.get("recipient_name") or "-")],
                [_quote_doc_text("identity_email", language=language), str(prospect_data.get("adult_email") or values.get("recipient_email") or "-")],
                [_quote_doc_text("identity_phone", language=language), str(prospect_data.get("adult_phone") or "-")],
                [_quote_doc_text("identity_address", language=language), str(prospect_data.get("adult_address") or "-")],
            ]
        )
    story.append(
        _table_for_pdf(
            ["", ""],
            identity_rows,
            width=content_width,
            styles=styles,
            col_widths=[0.32, 0.68],
        )
    )
    story.append(Spacer(1, 5))
    story.append(PageBreak())

    story.append(Paragraph(_quote_doc_text("section_courses_options", language=language), styles["h1"]))
    planning_rows: list[list[str]] = []
    for block in planning_blocks:
        planning_rows.append(
            _planning_block_pdf_row(
                block,
                selected_solfege_slot=selected_solfege_slot,
                language=language,
            )
        )
    story.append(
        _table_for_pdf(
            [
                _quote_doc_text("planning_activity", language=language),
                _quote_doc_text("planning_location", language=language),
                _quote_doc_text("planning_day", language=language),
                _quote_doc_text("planning_time", language=language),
                _quote_doc_text("planning_duration", language=language),
            ],
            planning_rows,
            width=content_width,
            styles=styles,
            col_widths=[0.37, 0.23, 0.12, 0.17, 0.11],
        )
    )

    story.append(Spacer(1, 6))
    story.append(Paragraph(_quote_doc_text("section_services", language=language), styles["h2"]))
    service_rows = [
        [
            _quote_line_display_title(line, language=language),
            _compact_quantity_label(line.quantity),
            f"{int(line.duration_minutes)} min" if line.duration_minutes else "-",
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))}%",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in services
    ]
    story.append(
        _table_for_pdf(
            [
                _quote_doc_text("planning_activity", language=language),
                _quote_doc_text("table_quantity", language=language),
                _quote_doc_text("planning_duration", language=language),
                _quote_doc_text("table_vat", language=language),
                _quote_doc_text("table_unit_price_ttc", language=language),
                _quote_doc_text("table_total_ttc", language=language),
            ],
            service_rows,
            width=content_width,
            styles=styles,
            col_widths=[0.32, 0.12, 0.11, 0.11, 0.16, 0.18],
        )
    )

    adjustment_rows = [
        [
            _quote_doc_text("fee_discount", language=language)
            if (line.line_type or "").strip().lower() == "discount"
            else _quote_doc_text("fee_surcharge", language=language)
            if (line.line_type or "").strip().lower() == "surcharge"
            else (
                _quote_doc_text("fee_discount", language=language)
                if (line.master_item_type or "").strip().lower() == "discount_rule"
                else _quote_doc_text("fee_surcharge", language=language)
            ),
            _quote_line_display_title(line, language=language),
            _compact_quantity_label(line.quantity),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))}%",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in adjustments
    ]
    if adjustment_rows:
        story.append(Spacer(1, 6))
        story.append(Paragraph(_quote_doc_text("section_adjustments", language=language), styles["h2"]))
        story.append(
            _table_for_pdf(
                [
                    _quote_doc_text("table_type", language=language),
                    _quote_doc_text("table_title", language=language),
                    _quote_doc_text("table_quantity", language=language),
                    _quote_doc_text("table_vat", language=language),
                    _quote_doc_text("table_unit_price_ttc", language=language),
                    _quote_doc_text("table_total_ttc", language=language),
                ],
                adjustment_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.12, 0.28, 0.11, 0.11, 0.17, 0.21],
            )
        )

    product_rows = [
        [
            {
                "text": _quote_line_display_title(line, language=language),
                "subtext": "\n".join(
                    _unique_text_parts(
                        line.description,
                        (
                            str(product_long_descriptions.get(line.product_id) or "").strip()
                            if line.product_id is not None
                            else ""
                        ),
                    )
                ),
            },
            _compact_quantity_label(line.quantity),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))}%",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in products
    ]
    if product_rows:
        story.append(Spacer(1, 6))
        story.append(Paragraph(_quote_doc_text("section_products", language=language), styles["h2"]))
        story.append(
            _table_for_pdf(
                [
                    _quote_doc_text("table_material", language=language),
                    _quote_doc_text("table_quantity", language=language),
                    _quote_doc_text("table_vat", language=language),
                    _quote_doc_text("table_unit_price_ttc", language=language),
                    _quote_doc_text("table_total_ttc", language=language),
                ],
                product_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.35, 0.12, 0.11, 0.18, 0.24],
            )
        )

    kit_rows = [
        [
            {
                "text": _quote_line_display_title(line, language=language),
                "subtext": "\n".join(
                    _unique_text_parts(
                        line.description,
                        (
                            str(kit_long_descriptions.get(line.kit_id) or "").strip()
                            if line.kit_id is not None
                            else ""
                        ),
                        (
                            f"{_quote_doc_text('kit_includes', language=language)} :\n" + "\n".join(kit_composition.get(line.kit_id, []))
                            if line.kit_id is not None and kit_composition.get(line.kit_id)
                            else ""
                        ),
                    )
                ),
            },
            _compact_quantity_label(line.quantity),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))}%",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in kits
    ]
    if kit_rows:
        story.append(Spacer(1, 6))
        story.append(Paragraph(_quote_doc_text("section_kits", language=language), styles["h2"]))
        story.append(
            _table_for_pdf(
                [
                    _quote_doc_text("table_kit", language=language),
                    _quote_doc_text("table_quantity", language=language),
                    _quote_doc_text("table_vat", language=language),
                    _quote_doc_text("table_unit_price_ttc", language=language),
                    _quote_doc_text("table_total_ttc", language=language),
                ],
                kit_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.35, 0.12, 0.11, 0.18, 0.24],
            )
        )

    other_fee_rows = [
        [
            _quote_line_display_title(line, language=language),
            _compact_quantity_label(line.quantity),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))}%",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in other_fees
    ]
    if other_fee_rows:
        story.append(Spacer(1, 6))
        story.append(Paragraph(_quote_doc_text("section_other_fees", language=language), styles["h2"]))
        story.append(
            _table_for_pdf(
                [
                    _quote_doc_text("table_title", language=language),
                    _quote_doc_text("table_quantity", language=language),
                    _quote_doc_text("table_vat", language=language),
                    _quote_doc_text("table_unit_price_ttc", language=language),
                    _quote_doc_text("table_total_ttc", language=language),
                ],
                other_fee_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.35, 0.12, 0.11, 0.18, 0.24],
            )
        )

    story.append(PageBreak())
    story.append(Paragraph(_quote_doc_text("financial_title", language=language), styles["h2"]))
    financial_rows: list[list[str]] = []
    if values.get("has_financial_adjustment") == "true":
        financial_rows.append([_quote_doc_text("financial_total_before_adjustment", language=language), f"{values.get('total_ttc_before_adjustment', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append([values.get("financial_adjustment_type_label", _quote_doc_text("financial_adjustment", language=language)), f"{values.get('financial_adjustment_amount_ttc', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append([_quote_doc_text("financial_impact", language=language), values.get("financial_adjustment_impact_label", "-")])
        effective_date = values.get("financial_adjustment_effective_date", "")
        if effective_date and effective_date != "-":
            financial_rows.append([_quote_doc_text("financial_adjustment_date", language=language), effective_date])
        financial_rows.append([_quote_doc_text("financial_total_ht_invoice", language=language), f"{values.get('total_ht_after_adjustment', values.get('total_ht', '0,00'))} {values.get('currency', 'EUR')}"])
        financial_rows.append([_quote_doc_text("financial_vat_invoice", language=language, rate=values.get('vat_rate', '0,00')), f"{values.get('vat_amount_after_adjustment', values.get('vat_amount', '0,00'))} {values.get('currency', 'EUR')}"])
        financial_rows.append([_quote_doc_text("financial_total_ttc_quote", language=language), f"{values.get('total_ttc_after_adjustment', values.get('total_ttc', '0,00'))} {values.get('currency', 'EUR')}"])
    else:
        financial_rows.append([_quote_doc_text("financial_total_ht", language=language), f"{values.get('total_ht', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append([_quote_doc_text("financial_vat", language=language, rate=values.get('vat_rate', '0,00')), f"{values.get('vat_amount', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append([_quote_doc_text("financial_total_ttc_quote", language=language), f"{values.get('total_ttc', '0,00')} {values.get('currency', 'EUR')}"])
    story.append(
        _table_for_pdf(
            ["", ""],
            financial_rows,
            width=content_width,
            styles=styles,
            col_widths=[0.58, 0.42],
        )
    )

    story.append(Spacer(1, 8))
    story.append(Paragraph(_quote_doc_text("payment_title", language=language), styles["h1"]))
    special_bank_transfer_deposit_lines = _bank_transfer_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=bool(context.get("deposit_enabled")),
        deposit_amount_ttc=_decimal_from_any(context.get("deposit_amount_ttc"), Decimal("0.00")),
        currency=str(values.get("currency") or "EUR"),
        payment_method_label=str(values.get("payment_method_label") or "-"),
        remaining_ttc_after_deposit=_decimal_from_any(context.get("remaining_ttc_after_deposit"), Decimal("0.00")),
        language=language,
    )
    special_card_deposit_lines = _card_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=bool(context.get("deposit_enabled")),
        deposit_amount_ttc=_decimal_from_any(context.get("deposit_amount_ttc"), Decimal("0.00")),
        currency=str(values.get("currency") or "EUR"),
        payment_method_label=str(values.get("payment_method_label") or "-"),
        remaining_ttc_after_deposit=_decimal_from_any(context.get("remaining_ttc_after_deposit"), Decimal("0.00")),
        language=language,
    )
    special_deposit_lines = special_bank_transfer_deposit_lines or special_card_deposit_lines
    check_payment_instruction_lines = _check_payment_instruction_lines(
        payment_method_label=str(values.get("payment_method_label") or "-"),
        schedule=schedule,
        legal_entity_name=_quote_legal_entity_name(db=db, quote=quote),
        has_deposit=bool(context.get("deposit_enabled")),
        deposit_amount_ttc=_decimal_from_any(context.get("deposit_amount_ttc"), Decimal("0.00")),
        currency=str(values.get("currency") or "EUR"),
        language=language,
    )
    payment_method_display_label = (
        str(values.get("payment_method_label", "-")).lower()
        if special_bank_transfer_deposit_lines
        else str(values.get("payment_method_label", "-"))
    )
    payment_method_code = str(values.get("payment_method") or context.get("payment_method") or "").strip().upper()
    payment_instruction = str(values.get("payment_instruction") or context.get("payment_instruction") or "").strip()
    if payment_method_code == CARD_4X_FEES_PAYMENT_METHOD and not payment_instruction:
        payment_instruction = CARD_4X_FEES_PAYMENT_INSTRUCTION
    schedule_visibility = _json_object(context.get("schedule_visibility"))
    show_schedule_pdf = _is_true(schedule_visibility.get(AUDIENCE_CLIENT_PDF, len(schedule) > 1))
    story.append(Paragraph(f"{_quote_doc_text('payment_method', language=language)} : {escape(payment_method_display_label)}", styles["text"]))
    if special_deposit_lines:
        for line in special_deposit_lines:
            story.append(Paragraph(escape(line), styles["text"]))
    for line in check_payment_instruction_lines:
        story.append(Paragraph(escape(line), styles["text"]))
    if payment_instruction:
        if payment_method_code == CARD_4X_FEES_PAYMENT_METHOD:
            for line in [item.strip() for item in payment_instruction.splitlines() if item.strip()]:
                story.append(Paragraph(escape(line), styles["text"]))
        else:
            story.append(
                Paragraph(
                    f"{_quote_doc_text('payment_instructions', language=language)} : {escape(payment_instruction)}",
                    styles["text"],
                )
            )
    if not special_deposit_lines and payment_method_code != CARD_4X_FEES_PAYMENT_METHOD:
        story.append(Paragraph(escape(values.get("payment_schedule_summary", _quote_doc_text("payment_not_scheduled", language=language))), styles["text"]))
    if not special_deposit_lines and show_schedule_pdf and len(schedule) > 1:
        schedule_rows = [
            [
                str(item.get("label") or "-"),
                f"{item.get('amount_ttc', '-')}" + (f" {item.get('currency')}" if item.get("currency") else ""),
                _schedule_due_label(item, language=language),
                str(item.get("payment_method") or "-"),
            ]
            for item in schedule
        ]
        story.append(
            _table_for_pdf(
                [
                    _quote_doc_text("schedule_label", language=language),
                    _quote_doc_text("schedule_amount", language=language),
                    _quote_doc_text("schedule_when", language=language),
                    _quote_doc_text("schedule_type", language=language),
                ],
                schedule_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.29, 0.18, 0.31, 0.22],
            )
        )
    option_blocks = [
        _apply_template("{solfege_block_html}", values=values, html_keys={"solfege_block_html"}, html_output=True).replace("<p>", "").replace("</p>", ""),
        _apply_template("{masterclass_block_html}", values=values, html_keys={"masterclass_block_html"}, html_output=True).replace("<p>", "").replace("</p>", ""),
        _apply_template(
            "{end_year_concert_block_html}",
            values=values,
            html_keys={"end_year_concert_block_html"},
            html_output=True,
        ).replace("<p>", "").replace("</p>", ""),
        _apply_template(
            "{end_year_concert_compact_notice_pdf_html}",
            values=values,
            html_keys={"end_year_concert_compact_notice_pdf_html"},
            html_output=True,
        ).replace("<p>", "").replace("</p>", ""),
        _apply_template("{pass_recup_block_html}", values=values, html_keys={"pass_recup_block_html"}, html_output=True).replace("<p>", "").replace("</p>", ""),
        _apply_template(
            "{pass_recup_compact_notice_pdf_html}",
            values=values,
            html_keys={"pass_recup_compact_notice_pdf_html"},
            html_output=True,
        ).replace("<p>", "").replace("</p>", ""),
    ]
    option_blocks = [block.strip() for block in option_blocks if str(block or "").strip()]
    if option_blocks:
        story.append(Spacer(1, 6))
        story.append(Paragraph(_quote_doc_text("options_title", language=language), styles["h2"]))
        for block_html in option_blocks:
            story.append(Paragraph(block_html, styles["text"]))

    story.append(PageBreak())
    story.append(Paragraph(_quote_doc_text("calendar_title", language=language), styles["h1"]))
    story.append(Paragraph(_quote_doc_text("calendar_overview", language=language, summary=escape(values.get('calendar_summary', '-'))), styles["text"]))
    grouped: dict[str, dict[tuple[int, int], set[int]]] = {}
    for session in sessions:
        parsed = _session_date_parts(session.get("date"))
        if parsed is None:
            continue
        year, month, day = parsed
        activity_label = str(session.get("activity_label") or "").strip() or _quote_doc_text("calendar_heading_default", language=language, index=1)
        location_label = str(session.get("location_label") or "").strip()
        title = f"{activity_label} · {location_label}" if location_label else activity_label
        grouped.setdefault(title, {}).setdefault((year, month), set()).add(day)
    for idx, title in enumerate(sorted(grouped.keys()), start=1):
        heading = _calendar_group_heading(title, idx, language=language)
        month_map = grouped[title]
        count = sum(len(days) for days in month_map.values())
        story.append(Spacer(1, 5))
        story.append(Paragraph(heading, styles["h3"]))
        story.append(
            _table_for_pdf(
                [
                    _quote_doc_text("calendar_course_place", language=language),
                    _quote_doc_text("calendar_course_count", language=language),
                ],
                [[heading, _quote_doc_text("calendar_course_count_value", language=language, count=count)]],
                width=content_width,
                styles=styles,
                col_widths=[0.70, 0.30],
            )
        )
        sem_rows: list[list[str]] = []
        for month_label, days in _calendar_semester_rows(month_map, semester=1, language=language):
            sem_rows.append([_quote_doc_text("semester_1", language=language), month_label, days])
        for month_label, days in _calendar_semester_rows(month_map, semester=2, language=language):
            sem_rows.append([_quote_doc_text("semester_2", language=language), month_label, days])
        if not sem_rows:
            sem_rows.append(["-", "-", _quote_doc_text("calendar_no_session_short", language=language)])
        story.append(
            _table_for_pdf(
                [
                    _quote_doc_text("table_semester", language=language),
                    _quote_doc_text("table_month", language=language),
                    _quote_doc_text("calendar_course_dates", language=language),
                ],
                sem_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.20, 0.20, 0.60],
            )
        )

    story.append(PageBreak())
    story.append(Paragraph(_quote_doc_text("terms_title", language=language), styles["h1"]))
    story.append(Paragraph(escape(cgv_label or _quote_doc_text("terms_version_unspecified", language=language)), styles["h3"]))
    story.extend(terms_flowables)

    def _on_page(canvas_obj: Any, document: SimpleDocTemplate) -> None:
        _draw_quote_pdf_header_footer(
            canvas_obj,
            document,
            quote_number=quote.quote_number or "-",
            quote_label=_quote_doc_text("cover_quote", language=language),
            logo_reader=logo_reader,
        )

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buffer.getvalue()


def render_quote_pdf_from_combined_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    combined_html: str,
    audience: str = DEFAULT_AUDIENCE,
) -> bytes:
    if audience == AUDIENCE_ADMIN_PREVIEW:
        html_pdf = _render_html_pdf_with_xhtml2pdf(combined_html)
        if html_pdf:
            return html_pdf
    return _render_quote_pdf_blocks(db=db, quote=quote, lines=lines, audience=audience)
