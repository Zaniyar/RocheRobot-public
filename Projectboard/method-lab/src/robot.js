// Gelenkgruppen des G1/Dex1 für das Bewegungsprofil. Ein Profil gilt auch für collect_gentle.py.
export const GROUPS = [
  {id: 'right_arm', label: 'Rechter Arm', dof: 7, action: 7},
  {id: 'right_gripper', label: 'Rechter Greifer', dof: 2, action: 1},
  {id: 'left_arm', label: 'Linker Arm', dof: 7, action: 7},
  {id: 'left_gripper', label: 'Linker Greifer', dof: 2, action: 1},
  {id: 'waist', label: 'Taille', dof: 3, action: 3},
  {id: 'legs', label: 'Beine, Laufpolicy', dof: 12, action: 0},
  {id: 'base', label: 'Basis, Gehen', dof: 0, action: 3, scene: false},
];

export function groupOfBody(name) {
  const side = name.startsWith('left_') ? 'left' : name.startsWith('right_') ? 'right' : null;
  if (side && name.includes('dex1')) return `${side}_gripper`;
  if (side && /shoulder|elbow|wrist/.test(name)) return `${side}_arm`;
  if (/hip|knee|ankle/.test(name)) return 'legs';
  if (/waist/.test(name)) return 'waist';
  return 'body';   // Rumpf, Kopf, Becken bewegen sich nur mit dem Stand oder Gehen
}

export function highlightFor(groups) {
  return {...groups, body: !!(groups.base || groups.legs)};
}

export function profileStatus(profile) {
  if (profile.groups.base) return 'walkonly';
  if (profile.groups.legs) return 'balance';
  if (!profile.groups.right_arm || !profile.groups.right_gripper) return 'nodemo';
  return profile.sway_mm ? 'emulated' : 'ready';
}

export const PROFILE_STATUS = {
  ready: {label: 'Sammler bereit', tone: 'good', text: 'collect_gentle.py kann mit diesem Profil Daten erzeugen.'},
  emulated: {label: 'Nur nachgestellt', tone: 'warn', text: 'Daten sind möglich, das Becken wird aber nur von aussen bewegt. Keine echte Balance.'},
  nodemo: {label: 'Ohne Demonstrator', tone: 'warn', text: 'Der sanfte Demonstrator greift rechts. Dieses Profil braucht Teleoperation, der Sammler lehnt es ab.'},
  balance: {label: 'Sim-zu-Sim, 100 von 200', tone: 'warn', text: 'Echte Laufpolicy in MuJoCo, kein Sturz. 100 von 200 sanft abgelegt, 48 verweigert, 7 mit Tischkontakt, 4 mit Selbstkollision. Daten nur aus bestandenen Läufen.'},
  walkonly: {label: 'Gehen ja, Greifen nein', tone: 'bad', text: 'Gehen läuft frei im Raum, Drehen aber kaum. Mit angehobenem Arm stoppt der Roboter nicht und drückt gegen den Tisch. Der Sammler lehnt das Profil ab.'},
  missing: {label: 'Szene kann das noch nicht', tone: 'bad', text: 'Diese Gelenke sind in der MuJoCo-Szene starr. Der Sammler lehnt das Profil ab, statt etwas vorzutäuschen.'},
};
