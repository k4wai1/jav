package normalizer

import (
	"crypto/sha256"
	"encoding/hex"
	"math"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
)

// Normalizer + tabla/zone puros (equiv. ui_normalizer.py + loop_helpers.py
// puro). Sin I/O, sin red, sin env: entra dump crudo, sale tabla.

// --- Constantes idénticas (spec §6.2) ---

const MaxCandidates = 254
const MaxTable = 254
const HoldsMax = 140
const DenseListMin = 3
const ProbSumTol = 0.025
const ArgmaxEps = 1e-6

// TAU vive aquí como constante documentada; el loop futuro la consume.
const TAU = 0.70

const InputTimeoutMs = 2500
const PollMs = 60

const PassMask = "a password, not read"
const EmptyFlags = "—"
const ZoneUnknown = "unknown"

var ZoneValues = []string{
	"top-left", "top-center", "top-right",
	"mid-left", "mid-center", "mid-right",
	"bottom-left", "bottom-center", "bottom-right",
}

var DecorSubstr = []string{"statusBarBackground", "navigationBarBackground"}

// Anti-ticker (spec tactical-robustness-p1p2 §2): relojes y porcentajes no
// cuentan como progreso de pantalla.
var volatileTextRe = regexp.MustCompile(`^(\d{1,2}:\d{2}(:\d{2})?|\d{1,3}\s*%)$`)

var Containers = map[string]bool{
	"android.widget.LinearLayout":               true,
	"android.widget.FrameLayout":                true,
	"android.widget.RelativeLayout":             true,
	"android.view.ViewGroup":                    true,
	"android.widget.ListView":                   true,
	"android.widget.GridView":                   true,
	"android.widget.ScrollView":                 true,
	"androidx.recyclerview.widget.RecyclerView": true,
	"androidx.viewpager.widget.ViewPager":       true,
}

// PasswordMarkers por categoría (sin literales de app).
var PasswordMarkers = []string{"password", "passwd", "passcode", "pin", "credential"}

var FastActions = []string{"TAP", "TYPE", "SCROLL_DOWN", "SCROLL_UP", "BACK"}

var DecisionActions = []string{"TAP", "TYPE", "SCROLL_DOWN", "SCROLL_UP", "BACK", "DONE", "ESCALATE"}

// SensitiveVerbs genéricos de categorías críticas (sin literales de app).
var SensitiveVerbs = []string{
	"enviar", "send", "mandar",
	"comprar", "buy", "pagar", "pay", "pago",
	"borrar", "eliminar", "delete", "suprimir",
	"cuenta", "account", "permiso", "permission",
}

// --- Tipos (equiv. state.py) ---

// Candidate es un nodo accionable normalizado.
type Candidate struct {
	ID         string
	Cls        string
	Text       string
	Desc       string
	ResourceID string
	Clickable  bool
	Editable   bool
	Focused    bool
	Scrollable bool
	Visible    bool
	Bounds     [4]int
}

func (c Candidate) ClassShort() string {
	if c.Cls == "" {
		return "View"
	}
	return c.Cls
}

func (c Candidate) Flags() string {
	return RowFlags(c.Clickable, c.Editable, c.Focused, c.Scrollable)
}

func (c Candidate) Compact() string {
	focus := ""
	if c.Editable && c.Focused {
		focus = " (focused)"
	}
	if c.Text != "" {
		return "[" + c.ID + "] " + c.Cls + " \"" + c.Text + "\"" + focus
	}
	if c.Desc != "" {
		return "[" + c.ID + "] " + c.Cls + " desc=\"" + c.Desc + "\""
	}
	rid := c.ResourceID
	if i := strings.LastIndex(rid, "/"); i >= 0 {
		rid = rid[i+1:]
	}
	if rid != "" {
		return "[" + c.ID + "] " + c.Cls + " id=" + rid
	}
	return "[" + c.ID + "] " + c.Cls
}

// FocusedField es el campo que recibiría typing (patrón A2).
type FocusedField struct {
	Label      string
	Kind       string
	Holds      string
	IsPassword bool
}

// AsView vista apta para S1/forense (sin secreto crudo).
func (f *FocusedField) AsView() map[string]any {
	if f == nil {
		return map[string]any{"label": "none", "kind": "none", "holds": "empty"}
	}
	if f.IsPassword {
		label := f.Label
		if label == "" {
			label = "none"
		}
		return map[string]any{"label": label, "kind": "password", "holds": PassMask}
	}
	label := f.Label
	if label == "" {
		label = "none"
	}
	kind := f.Kind
	if kind == "" {
		kind = "text"
	}
	holds := f.Holds
	if holds == "" {
		holds = "empty"
	}
	return map[string]any{"label": label, "kind": kind, "holds": holds}
}

// NormalizedState es el estado semántico normalizado.
type NormalizedState struct {
	Package      string
	Activity     string
	SnapshotID   int64
	Candidates   []Candidate
	RawCount     int
	ScreenHeight int
	ScreenWidth  int
	Focused      *FocusedField
}

func (s *NormalizedState) CompactLines() []string {
	out := make([]string, 0, len(s.Candidates))
	for _, c := range s.Candidates {
		out = append(out, c.Compact())
	}
	return out
}

func ShortClass(cls string) string {
	if i := strings.LastIndex(cls, "."); i >= 0 {
		cls = cls[i+1:]
	}
	cls = strings.TrimSpace(cls)
	if cls == "" {
		return "View"
	}
	return cls
}

func isPassword(class, rid, hint, desc string) bool {
	hay := strings.ToLower(class + " " + rid + " " + hint + " " + desc)
	for _, m := range PasswordMarkers {
		if strings.Contains(hay, m) {
			return true
		}
	}
	return false
}

func fieldLabel(text, desc, rid, id string) string {
	if t := strings.TrimSpace(text); t != "" {
		return t
	}
	if d := strings.TrimSpace(desc); d != "" {
		return d
	}
	if i := strings.LastIndex(rid, "/"); i >= 0 {
		return rid[i+1:]
	}
	return id
}

func strVal(n map[string]any, key string) string {
	if v, ok := n[key].(string); ok {
		return v
	}
	return ""
}

func boolVal(n map[string]any, key string) bool {
	if v, ok := n[key].(bool); ok {
		return v
	}
	return false
}

func theFocusedField(nodes []map[string]any) *FocusedField {
	var editables []map[string]any
	for _, n := range nodes {
		if boolVal(n, "editable") {
			editables = append(editables, n)
		}
	}
	if len(editables) == 0 {
		return nil
	}
	chosen := editables[0]
	for _, n := range editables {
		if boolVal(n, "focused") {
			chosen = n
			break
		}
	}
	secret := isPassword(strVal(chosen, "class"), strVal(chosen, "resource_id"),
		strVal(chosen, "hint"), strVal(chosen, "content_desc"))
	holds := strings.TrimSpace(strVal(chosen, "text"))
	if len(holds) > HoldsMax {
		holds = holds[:HoldsMax]
	}
	kind := "text"
	if secret {
		kind = "password"
	}
	return &FocusedField{
		Label:      fieldLabel(strVal(chosen, "text"), strVal(chosen, "content_desc"), strVal(chosen, "resource_id"), strVal(chosen, "id")),
		Kind:       kind,
		Holds:      holds,
		IsPassword: secret,
	}
}

func keep(n map[string]any) bool {
	rid := strVal(n, "resource_id")
	for _, d := range DecorSubstr {
		if strings.Contains(rid, d) {
			return false
		}
	}
	text := strings.TrimSpace(strVal(n, "text"))
	desc := strings.TrimSpace(strVal(n, "content_desc"))
	interactive := boolVal(n, "clickable") || boolVal(n, "editable") || boolVal(n, "scrollable")
	if !interactive && text == "" && desc == "" {
		return false
	}
	return true
}

func rank(c Candidate) int {
	if c.Editable {
		return 0
	}
	if c.Clickable && (c.Text != "" || c.Desc != "") {
		return 1
	}
	return 2
}

// rawNodes convierte nodes crudos a lista de mapas.
func rawNodes(dump map[string]any) []map[string]any {
	var out []map[string]any
	raw, ok := dump["nodes"].([]any)
	if !ok {
		return nil
	}
	for _, item := range raw {
		if m, ok := item.(map[string]any); ok {
			out = append(out, m)
		}
	}
	return out
}

func toInt64(v any) int64 {
	switch t := v.(type) {
	case int64:
		return t
	case int:
		return int64(t)
	case float64:
		return int64(t)
	case float32:
		return int64(t)
	}
	return 0
}

func toInt(v any) int {
	switch t := v.(type) {
	case int:
		return t
	case int64:
		return int(t)
	case float64:
		return int(t)
	case float32:
		return int(t)
	}
	return 0
}

// Normalize convierte dump crudo → estado (puro). Cadena: 500 raw → ≤254.
func Normalize(dump map[string]any, limit, screenH, screenW int) *NormalizedState {
	if limit <= 0 {
		limit = MaxCandidates
	}
	nodes := rawNodes(dump)
	var kept []Candidate
	for _, n := range nodes {
		if !keep(n) {
			continue
		}
		var b [4]int
		if raw, ok := n["bounds"].([]any); ok && len(raw) == 4 {
			for i := 0; i < 4; i++ {
				b[i] = toInt(raw[i])
			}
		}
		kept = append(kept, Candidate{
			ID:         strVal(n, "id"),
			Cls:        ShortClass(strVal(n, "class")),
			Text:       strings.TrimSpace(strVal(n, "text")),
			Desc:       strings.TrimSpace(strVal(n, "content_desc")),
			ResourceID: strVal(n, "resource_id"),
			Clickable:  boolVal(n, "clickable"),
			Editable:   boolVal(n, "editable"),
			Focused:    boolVal(n, "focused"),
			Scrollable: boolVal(n, "scrollable"),
			Visible:    boolValDefault(n, "visible", true),
			Bounds:     b,
		})
	}
	sort.SliceStable(kept, func(i, j int) bool { return rank(kept[i]) < rank(kept[j]) })
	if len(kept) > limit {
		kept = kept[:limit]
	}
	return &NormalizedState{
		Package:      strVal(dump, "package"),
		Activity:     strVal(dump, "activity"),
		SnapshotID:   toInt64(dump["snapshot_id"]),
		Candidates:   kept,
		RawCount:     len(nodes),
		ScreenHeight: screenH,
		ScreenWidth:  screenW,
		Focused:      theFocusedField(nodes),
	}
}

func boolValDefault(n map[string]any, key string, def bool) bool {
	if v, ok := n[key].(bool); ok {
		return v
	}
	return def
}

// FormatState render compacto.
func FormatState(s *NormalizedState) string {
	head := s.Package + " snap=" + itoa(s.SnapshotID) +
		" (" + itoa(int64(len(s.Candidates))) + "/" + itoa(int64(s.RawCount)) + ")"
	lines := append([]string{head}, s.CompactLines()...)
	return strings.Join(lines, "\n")
}

func itoa(v int64) string { return strconv.FormatInt(v, 10) }

func u64toa(v uint64) string { return strconv.FormatUint(v, 10) }

// --- Tabla (equiv. loop_helpers build_table / serialize_table) ---

// Row es una fila numerada 0..253.
type Row struct {
	Idx        int
	ID         string
	Label      string
	Text       string
	ResourceID string
	Bounds     [4]int
	Clickable  bool
	Editable   bool
	Focused    bool
	Scrollable bool
	Visible    bool
	ClassShort string
	Zone       string
	Flags      string
}

// RowFlags subset ordenado `click|edit|foc|scroll`; vacío = `—`.
func RowFlags(clickable, editable, focused, scrollable bool) string {
	var parts []string
	if clickable {
		parts = append(parts, "click")
	}
	if editable {
		parts = append(parts, "edit")
	}
	if focused {
		parts = append(parts, "foc")
	}
	if scrollable {
		parts = append(parts, "scroll")
	}
	if len(parts) == 0 {
		return EmptyFlags
	}
	return strings.Join(parts, "|")
}

// ZoneOf celda 3×3 EN desde centroide + resolución; unknown sin datos.
func ZoneOf(bounds [4]int, w, h int) string {
	if w <= 0 || h <= 0 {
		return ZoneUnknown
	}
	l, t, r, b := bounds[0], bounds[1], bounds[2], bounds[3]
	if !(r > l && b > t && l >= 0 && t >= 0) {
		return ZoneUnknown
	}
	cx := float64(l+r) / 2.0
	cy := float64(t+b) / 2.0
	var col string
	switch {
	case cx < float64(w)/3.0:
		col = "left"
	case cx < 2*float64(w)/3.0:
		col = "center"
	default:
		col = "right"
	}
	var row string
	switch {
	case cy < float64(h)/3.0:
		row = "top"
	case cy < 2*float64(h)/3.0:
		row = "mid"
	default:
		row = "bottom"
	}
	return row + "-" + col
}

// BuildTable poda a tabla numerada 0..253 (rows, byIdx).
func BuildTable(cands []Candidate, w, h int) ([]Row, map[int]Row) {
	n := len(cands)
	if n > MaxTable {
		n = MaxTable
	}
	rows := make([]Row, 0, n)
	byIdx := make(map[int]Row, n)
	for i := 0; i < n; i++ {
		c := cands[i]
		id := c.ID
		if id == "" {
			id = "n_" + u64toa(uint64(i))
		}
		label := c.Compact()
		rows = append(rows, Row{
			Idx: i, ID: id, Label: label, Text: c.Text,
			ResourceID: c.ResourceID, Bounds: c.Bounds,
			Clickable: c.Clickable, Editable: c.Editable,
			Focused: c.Focused, Scrollable: c.Scrollable,
			Visible: c.Visible, ClassShort: c.ClassShort(),
			Zone: ZoneOf(c.Bounds, w, h), Flags: c.Flags(),
		})
		byIdx[i] = rows[i]
	}
	return rows, byIdx
}

// SerializeTable filas enriquecidas para S1: [idx,class_short,zone,flags,label].
func SerializeTable(rows []Row) [][]any {
	out := make([][]any, 0, len(rows))
	for _, r := range rows {
		out = append(out, []any{r.Idx, r.ClassShort, r.Zone, r.Flags, r.Label})
	}
	return out
}

// confusableRoles glifos mono-carácter que colisionan en la tokenización
// del modelo (spec tactical-robustness-p1p2 §4).
var confusableRoles = map[string]string{
	"9": "digit nine",
	"×": "multiplication sign",
	"+": "plus sign",
	"-": "minus sign",
	"C": "clear",
	".": "decimal point",
}

// FormatCandidateLabel capa adaptadora de etiquetas para el modelo:
// amplía glifos ambiguos de una sola runa con sufijo de rol. NO la usa
// SerializeTable (paridad golden).
func FormatCandidateLabel(text string) string {
	t := strings.TrimSpace(text)
	if utf8.RuneCountInString(t) != 1 {
		return text
	}
	role, ok := confusableRoles[t]
	if !ok {
		return text
	}
	return t + " [" + role + "]"
}

// FirstResult hint del primer interactivo del contenedor principal (§12.2).
func FirstResult(rows []Row) (int, bool) {
	if len(rows) == 0 {
		return 0, false
	}
	hasScroll := false
	for _, r := range rows {
		if r.Scrollable {
			hasScroll = true
			break
		}
	}
	if !hasScroll {
		return 0, false
	}
	groups := map[string][]Row{}
	for _, r := range rows {
		if r.Visible && r.Clickable && strings.TrimSpace(r.Label) != "" {
			groups[r.ClassShort] = append(groups[r.ClassShort], r)
		}
	}
	var best []Row
	for _, members := range groups {
		if len(members) >= DenseListMin && len(members) > len(best) {
			best = members
		}
	}
	if len(best) == 0 {
		return 0, false
	}
	min := best[0].Idx
	for _, r := range best[1:] {
		if r.Idx < min {
			min = r.Idx
		}
	}
	return min, true
}

// FailInfo es un fallo estructural {code, error}.
type FailInfo struct {
	Code  string
	Error string
}

// CheckDecisionJSON valida JSON de decisión contra el enum S1.
func CheckDecisionJSON(dec map[string]any) *FailInfo {
	if dec == nil {
		return &FailInfo{Code: "JEV_HALLUCINATION", Error: "decisión no es objeto"}
	}
	action, _ := dec["action"].(string)
	valid := false
	for _, a := range DecisionActions {
		if a == action {
			valid = true
			break
		}
	}
	if !valid {
		return &FailInfo{Code: "JEV_HALLUCINATION", Error: "action fuera del enum"}
	}
	tgt := dec["target"]
	switch t := tgt.(type) {
	case string:
		if t != "NONE" {
			return &FailInfo{Code: "JEV_HALLUCINATION", Error: "target inválido (int|NONE)"}
		}
	case int:
		if t < 0 || t > MaxTable-1 {
			return &FailInfo{Code: "JEV_HALLUCINATION", Error: "target fuera de rango"}
		}
	case int64:
		if t < 0 || t > MaxTable-1 {
			return &FailInfo{Code: "JEV_HALLUCINATION", Error: "target fuera de rango"}
		}
	case float64:
		if t != math.Trunc(t) || t < 0 || t > MaxTable-1 {
			return &FailInfo{Code: "JEV_HALLUCINATION", Error: "target fuera de rango"}
		}
	default:
		return &FailInfo{Code: "JEV_HALLUCINATION", Error: "target inválido (int|NONE)"}
	}
	conf, ok := toFloat(dec["conf"])
	if !ok || math.IsNaN(conf) || math.IsInf(conf, 0) || conf < 0.0 || conf > 1.0 {
		return &FailInfo{Code: "JEV_HALLUCINATION", Error: "conf fuera de [0,1]"}
	}
	if _, ok := dec["needs_system_2"].(bool); !ok {
		if dec["needs_system_2"] != nil {
			return &FailInfo{Code: "JEV_HALLUCINATION", Error: "needs_system_2 no es bool"}
		}
	}
	return nil
}

func toFloat(v any) (float64, bool) {
	switch t := v.(type) {
	case float64:
		return t, true
	case float32:
		return float64(t), true
	case int:
		return float64(t), true
	case int64:
		return float64(t), true
	}
	return 0, false
}

// ValidateTarget validación estructural del target antes de mutar.
func ValidateTarget(row *Row, screenH int) *FailInfo {
	if row == nil {
		return &FailInfo{Code: "SELECTOR_NOT_FOUND", Error: "target NONE o ausente en la tabla vigente"}
	}
	if !row.Visible {
		return &FailInfo{Code: "SELECTOR_NOT_FOUND", Error: "nodo no visible en snapshot vigente: " + row.ID}
	}
	l, t, r, b := row.Bounds[0], row.Bounds[1], row.Bounds[2], row.Bounds[3]
	if !(r > l && b > t && l >= 0 && t >= 0) {
		return &FailInfo{Code: "SELECTOR_NOT_FOUND", Error: "coordenadas fuera de pantalla: " + row.ID}
	}
	if screenH > 0 && !(t < screenH && l < 4096) {
		return &FailInfo{Code: "SELECTOR_NOT_FOUND", Error: "nodo fuera de pantalla: " + row.ID}
	}
	return nil
}

// IsSensitive heurística genérica de acción crítica/irreversible (§7.2).
func IsSensitive(goal, targetLabel string) bool {
	hay := strings.ToLower(goal + " " + targetLabel)
	for _, v := range SensitiveVerbs {
		if strings.Contains(hay, v) {
			return true
		}
	}
	return false
}

// isVolatileNode true → el candidato NO entra en la firma de pantalla.
func isVolatileNode(c Candidate) bool {
	eff := c.Text
	if eff == "" {
		eff = c.Desc
	}
	t := strings.TrimSpace(eff)
	return t != "" && volatileTextRe.MatchString(t)
}

// ScreenFingerprint firma de pantalla por contenido (id+texto, sha256).
func ScreenFingerprint(cands []Candidate) string {
	type pair struct{ id, text string }
	pairs := make([]pair, 0, len(cands))
	for _, c := range cands {
		if isVolatileNode(c) {
			continue
		}
		t := c.Text
		if t == "" {
			t = c.Desc
		}
		pairs = append(pairs, pair{c.ID, t})
	}
	if len(pairs) == 0 {
		return ""
	}
	sort.Slice(pairs, func(i, j int) bool {
		if pairs[i].id == pairs[j].id {
			return pairs[i].text < pairs[j].text
		}
		return pairs[i].id < pairs[j].id
	})
	var sb strings.Builder
	for _, p := range pairs {
		sb.WriteString(p.id)
		sb.WriteString("=")
		sb.WriteString(p.text)
		sb.WriteString("|")
	}
	sum := sha256.Sum256([]byte(sb.String()))
	return hex.EncodeToString(sum[:])
}

// RunSignature firma fail-fast entre corridas (§12.3).
func BuildRunSignature(code, stalledStep string, snapFirst, snapLast int64, fpFirst, fpLast string) map[string]any {
	snapStalled := snapFirst == snapLast
	fpStalled := fpFirst != "" && fpFirst == fpLast
	return map[string]any{
		"code": code, "stalled_step": stalledStep,
		"snapshot_first": snapFirst, "snapshot_last": snapLast,
		"fingerprint_first": fpFirst, "fingerprint_last": fpLast,
		"progress": !(snapStalled || fpStalled),
	}
}

// SameSignature true si dos firmas son la misma (§12.3).
func SameSignature(a, b map[string]any) bool {
	if a == nil || b == nil {
		return false
	}
	ca, _ := a["code"].(string)
	cb, _ := b["code"].(string)
	if ca == "" || ca != cb {
		return false
	}
	sa, _ := a["stalled_step"].(string)
	sb, _ := b["stalled_step"].(string)
	if sa != "" && sa == sb {
		return true
	}
	fa1, _ := a["fingerprint_first"].(string)
	fa2, _ := a["fingerprint_last"].(string)
	fb1, _ := b["fingerprint_first"].(string)
	fb2, _ := b["fingerprint_last"].(string)
	if fa1 != "" && fa1 == fa2 && fa1 == fb1 && fa2 == fb2 {
		return true
	}
	return false
}

func rowSecret(classShort, resourceID, label string) bool {
	hay := strings.ToLower(classShort + " " + resourceID + " " + label)
	for _, m := range PasswordMarkers {
		if strings.Contains(hay, m) {
			return true
		}
	}
	return false
}

// FocusedFieldView vista {label, holds} del campo enfocado (P0-1, puro).
func FocusedFieldView(rows []Row) map[string]any {
	var editables []Row
	for _, r := range rows {
		if r.Editable {
			editables = append(editables, r)
		}
	}
	if len(editables) == 0 {
		return map[string]any{"label": "none", "holds": "empty"}
	}
	chosen := editables[0]
	for _, r := range editables {
		if r.Focused {
			chosen = r
			break
		}
	}
	label := chosen.Label
	if label == "" {
		label = chosen.ID
	}
	if label == "" {
		label = "none"
	}
	if rowSecret(chosen.ClassShort, chosen.ResourceID, chosen.Label) {
		return map[string]any{"label": label, "holds": PassMask}
	}
	text := chosen.Text
	if len(text) > HoldsMax {
		text = text[:HoldsMax]
	}
	if text == "" && chosen.Label != "" {
		text = chosen.Label
		if len(text) > HoldsMax {
			text = text[:HoldsMax]
		}
	}
	if text == "" {
		text = "empty"
	}
	return map[string]any{"label": label, "holds": text}
}

// PrepareInputVerification target exact-span para read-back tras TYPE (M2).
func PrepareInputVerification(row *Row, text string) map[string]any {
	if row == nil || !row.Editable {
		return nil
	}
	if text == "" || rowSecret(row.ClassShort, row.ResourceID, row.Label) {
		return nil
	}
	return map[string]any{
		"target": map[string]any{
			"id": row.ID, "resource_id": row.ResourceID,
			"hint":   row.Label,
			"bounds": []int{row.Bounds[0], row.Bounds[1], row.Bounds[2], row.Bounds[3]},
		},
		"text": text,
	}
}

// InputMatches exact-span: misma identidad Y text==esperado en exactamente 1.
func InputMatches(cands []map[string]any, verification map[string]any) bool {
	if verification == nil {
		return false
	}
	target, _ := verification["target"].(map[string]any)
	want, _ := verification["text"].(string)
	var tid, trid, thint string
	var tbounds []int
	if target != nil {
		tid, _ = target["id"].(string)
		trid, _ = target["resource_id"].(string)
		thint, _ = target["hint"].(string)
		if b, ok := target["bounds"].([]int); ok {
			tbounds = b
		}
	}
	hits := 0
	for _, c := range cands {
		rid, _ := c["resource_id"].(string)
		same := trid != "" && rid != "" && rid == trid
		if !same && trid == "" {
			cid, _ := c["id"].(string)
			clabel, _ := c["label"].(string)
			var cb []int
			if b, ok := c["bounds"].([]int); ok {
				cb = b
			}
			same = cid == tid && clabel == thint && intSliceEq(cb, tbounds)
		}
		ctext, _ := c["text"].(string)
		if same && ctext == want {
			hits++
		}
	}
	return hits == 1
}

func intSliceEq(a, b []int) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
