export const roleNames = { clinic_admin: 'Clinic administrator', doctor: 'Doctor', nurse: 'Nurse', receptionist: 'Receptionist', billing_staff: 'Billing', patient: 'Patient', super_admin: 'Platform owner' };
export const navByRole = {
  clinic_admin: [['Overview','grid'],['Patients','users'],['Appointments','calendar'],['Messages','message'],['Team access','team'],['Imports','upload'],['Clinic setup','settings'],['Audit log','note']],
  doctor: [['Overview','grid'],['My patients','users'],['Appointments','calendar'],['Messages','message'],['Visit notes','note']],
  nurse: [['Overview','grid'],['My patients','users'],['Appointments','calendar'],['Messages','message'],['Vitals','pulse']],
  receptionist: [['Overview','grid'],['Patients','users'],['Appointments','calendar'],['Waiting room','room'],['Waitlist','calendar'],['Messages','message']],
  billing_staff: [['Overview','grid'],['Claims','receipt'],['Messages','message']],
  patient: [['My care','grid'],['Appointments','calendar'],['Messages','message'],['Health records','note']],
  super_admin: [['Overview','grid'],['Clinics','building'],['Users','team']],
};
