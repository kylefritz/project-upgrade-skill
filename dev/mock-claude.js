// A stand-in for the claude.ai artifact runtime, for previewing the pages locally.
// Implements just the parts of `db` and `user` the pages call, over window.DEMO_DATA
// ({ "<collection>/<doc>": {...} }). Writes stay in memory and fire the listeners,
// so Approve, Feedback and notes can be clicked through. Never used in production.
(() => {
  const store = new Map(Object.entries(window.DEMO_DATA || {}));
  const listeners = new Set();
  const meta = { fromCache: false, hasPendingWrites: false };
  const snap = (path) => {
    const id = path.split("/").pop(), body = store.get(path);
    return { id, exists: body !== undefined, data: () => body, metadata: meta };
  };
  const inColl = (coll) => [...store.keys()].filter((k) => k.slice(0, k.lastIndexOf("/")) === coll).sort();
  const fire = () => setTimeout(() => listeners.forEach((l) => l()), 0);
  const docRef = (path) => ({
    id: path.split("/").pop(), path,
    get: async () => snap(path),
    set: async (data) => { store.set(path, JSON.parse(JSON.stringify(data))); fire(); },
    update: async (data) => { if (!store.has(path)) throw { code: "invalid_argument", message: "missing" }; store.set(path, { ...store.get(path), ...data }); fire(); },
    delete: async () => { store.delete(path); fire(); },
    onSnapshot(next) { const l = () => next(snap(path)); listeners.add(l); setTimeout(l, 30); return () => listeners.delete(l); },
  });
  const collRef = (path) => ({
    path,
    doc: (id) => docRef(path + "/" + (id || Math.random().toString(36).slice(2, 12))),
    add: async (data) => { const r = docRef(path + "/" + Math.random().toString(36).slice(2, 12)); await r.set(data); return r; },
    onSnapshot(next) {
      const l = () => { const docs = inColl(path).map(snap); next({ docs, size: docs.length, empty: !docs.length, docChanges: () => [], metadata: meta }); };
      listeners.add(l); setTimeout(l, 30); return () => listeners.delete(l);
    },
  });
  const db = { doc: docRef, collection: collRef };
  const people = { u_demo_owner: "Sam Rivera" };
  const user = {
    id: async () => "u_demo_owner", isOwner: async () => true, canEdit: async () => true, can: async () => true,
    me: async () => ({ id: "u_demo_owner", name: people.u_demo_owner, isOwner: true, canEdit: true }),
    profiles: async (ids) => Object.fromEntries([].concat(ids).map((id) => [id, { id, name: people[id] || "", isMe: id === "u_demo_owner" }])),
  };
  window.claude = { use: async (name) => (name === "db" ? db : name === "user" ? user : null) };
})();
