import Mathlib.Tactic
import Mathlib.Data.Real.Basic

/-!
Algebraic core of Supplement P6. U is an abstract real endpoint sequence;
the statistical coverage theorem and Python implementation are not axioms
of this development and are not claimed to be verified here.
-/
namespace MIC5090

def Lower (n : ℕ) (U : ℕ → ℝ) (x : ℕ) : ℝ := 1 - U (n-x)

theorem decreasing_slopes (n : ℕ) (U : ℕ → ℝ)
    (hc : ∀ i, i+2 ≤ n → U (i+2)-U (i+1) ≤ U (i+1)-U i)
    (x y : ℕ) (hxy : x ≤ y) (hy : y < n) :
    U (y+1)-U y ≤ U (x+1)-U x := by
  induction y, hxy using Nat.le_induction with
  | base => exact le_refl _
  | succ y hxy ih =>
    have hs := hc y (by omega)
    have hp := ih (by omega)
    linarith

theorem decreasing_increments (n : ℕ) (U : ℕ → ℝ)
    (hc : ∀ i, i+2 ≤ n → U (i+2)-U (i+1) ≤ U (i+1)-U i)
    (x y d : ℕ) (hxy : x ≤ y) (hyn : y+d ≤ n) :
    U (y+d)-U y ≤ U (x+d)-U x := by
  induction d with
  | zero => simp
  | succ d ih =>
    have hp := ih (by omega)
    have hs := decreasing_slopes n U hc (x+d) (y+d) (by omega) (by omega)
    simp only [Nat.add_assoc] at *
    linarith

theorem increment_bounds (n : ℕ) (U : ℕ → ℝ)
    (hc : ∀ i, i+2 ≤ n → U (i+2)-U (i+1) ≤ U (i+1)-U i)
    (hn : U n = 1) (h0 : 0 ≤ U 0)
    (x d : ℕ) (hxd : x+d ≤ n) :
    Lower n U d ≤ U (x+d)-U x ∧ U (x+d)-U x ≤ U d := by
  have hu := decreasing_increments n U hc 0 x d (by omega) hxd
  have hl := decreasing_increments n U hc x (n-d) d (by omega) (by omega)
  have he : n-d+d = n := by omega
  simp only [Nat.zero_add, he, hn] at hu hl
  unfold Lower
  constructor <;> linarith

theorem crossing_anchor_bounds (n : ℕ) (U : ℕ → ℝ)
    (hc : ∀ i, i+2 ≤ n → U (i+2)-U (i+1) ≤ U (i+1)-U i)
    (hn : U n = 1) (h0 : 0 ≤ U 0)
    (x y : ℕ) (hxy : x+y ≤ n) :
    Lower n U (x+y) ≤ Lower n U x + U y ∧
    Lower n U x + U y ≤ U (x+y) := by
  have ha := increment_bounds n U hc hn h0 (n-(x+y)) y (by omega)
  have hb := increment_bounds n U hc hn h0 y x (by omega)
  have he : n-(x+y)+y = n-x := by omega
  have he2 : y+x = x+y := by omega
  simp only [he, he2] at ha hb
  unfold Lower at *
  constructor <;> linarith

theorem lower_increment_bounds (n : ℕ) (U : ℕ → ℝ)
    (hc : ∀ i, i+2 ≤ n → U (i+2)-U (i+1) ≤ U (i+1)-U i)
    (hn : U n = 1) (h0 : 0 ≤ U 0)
    (x d : ℕ) (hxd : x+d ≤ n) :
    Lower n U d ≤ Lower n U (x+d)-Lower n U x ∧
    Lower n U (x+d)-Lower n U x ≤ U d := by
  have h := increment_bounds n U hc hn h0 (n-(x+d)) d (by omega)
  have he : n-(x+d)+d = n-x := by omega
  simp only [he] at h
  unfold Lower at *
  constructor <;> linarith [h.1, h.2]

theorem bracket_certificate (u lower upper : ℕ → ℝ) (n : ℕ)
    (hl : ∀ i, i ≤ n → lower i ≤ u i)
    (hu : ∀ i, i ≤ n → u i ≤ upper i)
    (hm : ∀ i, i+2 ≤ n → upper i + upper (i+2) ≤ 2*lower (i+1)) :
    ∀ i, i+2 ≤ n → u (i+2)-u (i+1) ≤ u (i+1)-u i := by
  intro i hi
  have h1 := hu i (by omega)
  have h2 := hl (i+1) (by omega)
  have h3 := hu (i+2) hi
  have h4 := hm i hi
  linarith

theorem count_row_feasible {I : Type*} (D : I → I → ℤ)
    (closed : ∀ a b c, D a c ≤ D a b + D b c) (v z a b : I) :
    (D v b-D v z) - (D v a-D v z) ≤ D a b := by
  have h := closed v a b
  omega

theorem count_row_attains_upper {I : Type*} (D : I → I → ℤ)
    (diagonal : ∀ a, D a a = 0) (z a b : I) :
    (D a b-D a z) - (D a a-D a z) = D a b := by
  rw [diagonal]
  omega

theorem count_row_attains_lower {I : Type*} (D : I → I → ℤ)
    (diagonal : ∀ a, D a a = 0) (z a b : I) :
    (D b b-D b z) - (D b a-D b z) = -D b a := by
  rw [diagonal]
  omega

theorem terminal_row_duplicate {I : Type*} (D : I → I → ℤ)
    (closed : ∀ a b c, D a c ≤ D a b + D b c)
    (z t : I) (n : ℤ) (hzt : D z t = n) (htz : D t z = -n)
    (j : I) : D t j = D z j-n := by
  have h1 := closed t z j
  have h2 := closed z t j
  rw [htz] at h1
  rw [hzt] at h2
  omega

def Anchored (n : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ) (v j : ℕ) : ℝ :=
  if j < v then -Lower n U (S v-S j)
  else if j = v then 0 else U (S j-S v)

theorem endpoint_order (n : ℕ) (U : ℕ → ℝ)
    (hc : ∀ i, i+2 ≤ n → U (i+2)-U (i+1) ≤ U (i+1)-U i)
    (hn : U n = 1) (h0 : 0 ≤ U 0) (d : ℕ) (hd : d ≤ n) :
    Lower n U d ≤ U d := by
  have h := increment_bounds n U hc hn h0 0 d (by omega)
  simpa using le_trans h.1 h.2

/-- The explicit vector in P6 satisfies every contiguous-range band. -/
theorem anchored_range_bounds (n k : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ)
    (hc : ∀ i, i+2 ≤ n → U (i+2)-U (i+1) ≤ U (i+1)-U i)
    (hn : U n = 1) (h0 : 0 ≤ U 0)
    (hS : ∀ i j, i ≤ j → j ≤ k → S i ≤ S j)
    (hSn : ∀ j, j ≤ k → S j ≤ n)
    (v i j : ℕ) (hv : v ≤ k) (hij : i < j) (hjk : j ≤ k) :
    Lower n U (S j-S i) ≤ Anchored n U S v j-Anchored n U S v i ∧
    Anchored n U S v j-Anchored n U S v i ≤ U (S j-S i) := by
  have hsij := hS i j (by omega) hjk
  have hsjn := hSn j hjk
  have hsvn := hSn v hv
  by_cases hjv : j < v
  · have hiv : i < v := by omega
    have hsjv := hS j v (by omega) hv
    have h := lower_increment_bounds n U hc hn h0 (S v-S j) (S j-S i) (by omega)
    have he : S v-S j+(S j-S i) = S v-S i := by omega
    rw [he] at h
    simp only [Anchored, if_pos hjv, if_pos hiv]
    constructor <;> linarith [h.1,h.2]
  · by_cases hiv : i < v
    · have hsiv := hS i v (by omega) hv
      by_cases hej : j = v
      · subst j
        have ho := endpoint_order n U hc hn h0 (S v-S i) (by omega)
        simp only [Anchored, lt_self_iff_false, ↓reduceIte, if_pos hiv, sub_neg_eq_add, zero_add]
        exact ⟨le_refl _,ho⟩
      · have hsjv := hS v j (by omega) hjk
        have h := crossing_anchor_bounds n U hc hn h0 (S v-S i) (S j-S v) (by omega)
        have he : S v-S i+(S j-S v) = S j-S i := by omega
        rw [he] at h
        simp only [Anchored, if_neg hjv, if_neg hej, if_pos hiv]
        constructor <;> linarith [h.1,h.2]
    · have hjne : j ≠ v := by omega
      by_cases hei : i = v
      · subst i
        have ho := endpoint_order n U hc hn h0 (S j-S v) (by omega)
        simp only [Anchored, if_neg hjv, if_neg hjne, lt_self_iff_false, ↓reduceIte, sub_zero]
        exact ⟨ho,le_refl _⟩
      · have hsvi := hS v i (by omega) (by omega)
        have h := increment_bounds n U hc hn h0 (S i-S v) (S j-S i) (by omega)
        have he : S i-S v+(S j-S i) = S j-S v := by omega
        rw [he] at h
        simpa only [Anchored, if_neg hjv, if_neg hjne, if_neg hiv, if_neg hei] using h

theorem anchored_total (n k : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ)
    (hn : U n = 1) (hz : S 0 = 0) (hk : S k = n)
    (v : ℕ) (hv : v < k) (hsv : S v ≤ n) :
    Anchored n U S v k-Anchored n U S v 0 = 1 := by
  by_cases hvz : v = 0
  · subst v
    simp [Anchored, show ¬k < 0 by omega, show k ≠ 0 by omega, hk, hz, hn]
  · simp only [Anchored, if_neg (show ¬k < v by omega), if_neg (show k ≠ v by omega),
      if_pos (show 0 < v by omega), hk, hz, Nat.sub_zero, Lower]
    ring

theorem anchored_upper_attainment (n : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ)
    (v j : ℕ) (hvj : v < j) :
    Anchored n U S v j-Anchored n U S v v = U (S j-S v) := by
  simp [Anchored, show ¬j < v by omega, show j ≠ v by omega]

theorem anchored_lower_attainment (n : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ)
    (v i : ℕ) (hiv : i < v) :
    Anchored n U S v v-Anchored n U S v i = Lower n U (S v-S i) := by
  simp [Anchored,hiv]

theorem anchored_nonnegative (n k : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ)
    (hc : ∀ i, i+2 ≤ n → U (i+2)-U (i+1) ≤ U (i+1)-U i)
    (hn : U n = 1) (h0 : 0 ≤ U 0)
    (hU : ∀ x, x ≤ n → U x ≤ 1)
    (hS : ∀ i j, i ≤ j → j ≤ k → S i ≤ S j)
    (hSn : ∀ j, j ≤ k → S j ≤ n)
    (v i : ℕ) (hv : v ≤ k) (hi : i < k) :
    0 ≤ Anchored n U S v (i+1)-Anchored n U S v i := by
  have h := anchored_range_bounds n k U S hc hn h0 hS hSn v i (i+1) hv (by omega) (by omega)
  have hu := hU (n-(S (i+1)-S i)) (by omega)
  unfold Lower at h
  linarith [h.1]

/-- A selected family indexed by the K nonterminal anchors has size at most K. -/
theorem selected_family_size {H : Type*} [DecidableEq H] (rows : ℕ → H) (k : ℕ) :
    ((Finset.range k).image rows).card ≤ k := by
  exact le_trans (Finset.card_image_le) (by simp)

/-- Attained bounds certify a projection; this does not identify the whole set. -/
theorem projection_certificate {X : Type*} (R : Set X) (f : X → ℝ) (l u : ℝ)
    (bound : ∀ x ∈ R, l ≤ f x ∧ f x ≤ u)
    (wl : ∃ x ∈ R, f x = l) (wu : ∃ x ∈ R, f x = u) :
    IsLeast (f '' R) l ∧ IsGreatest (f '' R) u := by
  constructor
  · constructor
    · rcases wl with ⟨x,hx,he⟩
      exact ⟨x,hx,he⟩
    · intro y hy
      rcases hy with ⟨x,hx,rfl⟩
      exact (bound x hx).1
  · constructor
    · rcases wu with ⟨x,hx,he⟩
      exact ⟨x,hx,he⟩
    · intro y hy
      rcases hy with ⟨x,hx,rfl⟩
      exact (bound x hx).2

/-! The following bridge exposes the weaker sufficient hypothesis used by the
population construction. Concavity remains one sufficient route to it. -/

def IncrementAdmissible (n : ℕ) (U : ℕ → ℝ) : Prop :=
  ∀ x d, x+d ≤ n →
    Lower n U d ≤ U (x+d)-U x ∧ U (x+d)-U x ≤ U d

theorem concavity_implies_increment_admissible (n : ℕ) (U : ℕ → ℝ)
    (hc : ∀ i, i+2 ≤ n → U (i+2)-U (i+1) ≤ U (i+1)-U i)
    (hn : U n = 1) (h0 : 0 ≤ U 0) : IncrementAdmissible n U := by
  exact increment_bounds n U hc hn h0

theorem lower_increment_bounds_of_admissible (n : ℕ) (U : ℕ → ℝ)
    (ha : IncrementAdmissible n U) (x d : ℕ) (hxd : x+d ≤ n) :
    Lower n U d ≤ Lower n U (x+d)-Lower n U x ∧
    Lower n U (x+d)-Lower n U x ≤ U d := by
  have h := ha (n-(x+d)) d (by omega)
  have he : n-(x+d)+d = n-x := by omega
  rw [he] at h
  unfold Lower at *
  constructor <;> linarith [h.1, h.2]

theorem crossing_bounds_of_admissible (n : ℕ) (U : ℕ → ℝ)
    (ha : IncrementAdmissible n U) (x y : ℕ) (hxy : x+y ≤ n) :
    Lower n U (x+y) ≤ Lower n U x + U y ∧
    Lower n U x + U y ≤ U (x+y) := by
  have h1 := ha (n-(x+y)) y (by omega)
  have h2 := ha y x (by omega)
  have he : n-(x+y)+y = n-x := by omega
  have he2 : y+x = x+y := by omega
  rw [he] at h1
  rw [he2] at h2
  unfold Lower at *
  constructor <;> linarith [h1.1, h1.2, h2.1, h2.2]

theorem endpoint_order_of_admissible (n : ℕ) (U : ℕ → ℝ)
    (ha : IncrementAdmissible n U) (d : ℕ) (hd : d ≤ n) :
    Lower n U d ≤ U d := by
  have h := ha 0 d (by omega)
  exact le_trans h.1 h.2

/-- Increment admissibility is enough for every contiguous probability band. -/
theorem anchored_range_bounds_of_admissible (n k : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ)
    (ha : IncrementAdmissible n U)
    (hS : ∀ i j, i ≤ j → j ≤ k → S i ≤ S j)
    (hSn : ∀ j, j ≤ k → S j ≤ n)
    (v i j : ℕ) (hv : v ≤ k) (hij : i < j) (hjk : j ≤ k) :
    Lower n U (S j-S i) ≤ Anchored n U S v j-Anchored n U S v i ∧
    Anchored n U S v j-Anchored n U S v i ≤ U (S j-S i) := by
  have hsij := hS i j (by omega) hjk
  have hsjn := hSn j hjk
  have hsvn := hSn v hv
  by_cases hjv : j < v
  · have hiv : i < v := by omega
    have hsjv := hS j v (by omega) hv
    have h := lower_increment_bounds_of_admissible n U ha (S v-S j) (S j-S i) (by omega)
    have he : S v-S j+(S j-S i) = S v-S i := by omega
    rw [he] at h
    simp only [Anchored, if_pos hjv, if_pos hiv]
    constructor <;> linarith [h.1, h.2]
  · by_cases hiv : i < v
    · have hsiv := hS i v (by omega) hv
      by_cases hej : j = v
      · subst j
        have ho := endpoint_order_of_admissible n U ha (S v-S i) (by omega)
        simp only [Anchored, lt_self_iff_false, ↓reduceIte, if_pos hiv, sub_neg_eq_add, zero_add]
        exact ⟨le_refl _, ho⟩
      · have hsjv := hS v j (by omega) hjk
        have h := crossing_bounds_of_admissible n U ha (S v-S i) (S j-S v) (by omega)
        have he : S v-S i+(S j-S v) = S j-S i := by omega
        rw [he] at h
        simp only [Anchored, if_neg hjv, if_neg hej, if_pos hiv]
        constructor <;> linarith [h.1, h.2]
    · have hjne : j ≠ v := by omega
      by_cases hei : i = v
      · subst i
        have ho := endpoint_order_of_admissible n U ha (S j-S v) (by omega)
        simp only [Anchored, if_neg hjv, if_neg hjne, lt_self_iff_false, ↓reduceIte, sub_zero]
        exact ⟨ho, le_refl _⟩
      · have hsvi := hS v i (by omega) (by omega)
        have h := ha (S i-S v) (S j-S i) (by omega)
        have he : S i-S v+(S j-S i) = S j-S v := by omega
        rw [he] at h
        simpa only [Anchored, if_neg hjv, if_neg hjne, if_neg hiv, if_neg hei] using h

def NormalizedAnchor (n : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ) (v j : ℕ) : ℝ :=
  Anchored n U S v j-Anchored n U S v 0

/-- Cumulative form of a probability vector satisfying every range band. -/
def CompleteRegion (n k : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ) : Set (ℕ → ℝ) :=
  {T | T 0 = 0 ∧ T k = 1 ∧ (∀ i, i < k → 0 ≤ T (i+1)-T i) ∧
    ∀ i j, i < j → j ≤ k →
      Lower n U (S j-S i) ≤ T j-T i ∧ T j-T i ≤ U (S j-S i)}

/-- The construction is a member of the full-histogram population region. -/
theorem normalized_anchor_member (n k : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ)
    (ha : IncrementAdmissible n U) (hn : U n = 1)
    (hU : ∀ x, x ≤ n → U x ≤ 1)
    (hS : ∀ i j, i ≤ j → j ≤ k → S i ≤ S j)
    (hSn : ∀ j, j ≤ k → S j ≤ n)
    (hz : S 0 = 0) (hk : S k = n) (v : ℕ) (hv : v < k) :
    NormalizedAnchor n U S v ∈ CompleteRegion n k U S := by
  have hb := anchored_range_bounds_of_admissible n k U S ha hS hSn v
  refine ⟨by simp [NormalizedAnchor], ?_, ?_, ?_⟩
  · exact anchored_total n k U S hn hz hk v hv (hSn v (by omega))
  · intro i hi
    have h := hb i (i+1) (by omega) (by omega) (by omega)
    have hu := hU (n-(S (i+1)-S i)) (by omega)
    unfold Lower at h
    unfold NormalizedAnchor
    linarith [h.1]
  · intro i j hij hjk
    have h := hb i j (by omega) hij hjk
    unfold NormalizedAnchor
    constructor <;> linarith [h.1, h.2]

/-- This assembled theorem applies the implemented concavity precondition. -/
theorem normalized_anchor_member_of_concavity (n k : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ)
    (hc : ∀ i, i+2 ≤ n → U (i+2)-U (i+1) ≤ U (i+1)-U i)
    (hn : U n = 1) (h0 : 0 ≤ U 0) (hU : ∀ x, x ≤ n → U x ≤ 1)
    (hS : ∀ i j, i ≤ j → j ≤ k → S i ≤ S j)
    (hSn : ∀ j, j ≤ k → S j ≤ n)
    (hz : S 0 = 0) (hk : S k = n) (v : ℕ) (hv : v < k) :
    NormalizedAnchor n U S v ∈ CompleteRegion n k U S := by
  exact normalized_anchor_member n k U S
    (concavity_implies_increment_admissible n U hc hn h0) hn hU hS hSn hz hk v hv

/-- The initial anchor attains the lower endpoint of a proper terminal range. -/
theorem normalized_terminal_lower_attainment (n k : ℕ) (U : ℕ → ℝ) (S : ℕ → ℕ)
    (hn : U n = 1) (hz : S 0 = 0) (hk : S k = n)
    (i : ℕ) (hi : 0 < i) (hik : i < k) (hSi : S i ≤ n) :
    NormalizedAnchor n U S 0 k-NormalizedAnchor n U S 0 i =
      Lower n U (n-S i) := by
  have he : n-(n-S i) = S i := by omega
  simp [NormalizedAnchor, Anchored, Lower, hz, hk, hn, he,
    show k ≠ 0 by omega, show i ≠ 0 by omega]

/-- Non-vacuity and strict weakening: admissibility need not imply concavity. -/
noncomputable def NonconcaveExample (x : ℕ) : ℝ :=
  match x with
  | 0 => 2/5
  | 1 => 3/5
  | 2 => 7/10
  | 3 => 9/10
  | _ => 1

theorem nonconcave_example_admissible : IncrementAdmissible 4 NonconcaveExample := by
  intro x d hd
  have hx : x ≤ 4 := by omega
  have hd4 : d ≤ 4 := by omega
  interval_cases x <;> interval_cases d <;> norm_num [NonconcaveExample, Lower] at *

theorem nonconcave_example_endpoints :
    NonconcaveExample 4 = 1 ∧
    (∀ x, x ≤ 4 → 0 ≤ NonconcaveExample x ∧ NonconcaveExample x ≤ 1) ∧
    (∀ x y, x ≤ y → y ≤ 4 → NonconcaveExample x ≤ NonconcaveExample y) := by
  constructor
  · norm_num [NonconcaveExample]
  constructor
  · intro x hx
    interval_cases x <;> norm_num [NonconcaveExample]
  · intro x y hxy hy
    have hx : x ≤ 4 := by omega
    interval_cases x <;> interval_cases y <;> norm_num [NonconcaveExample] at *

theorem nonconcave_example_fails_concavity :
    ¬ (∀ i, i+2 ≤ 4 → NonconcaveExample (i+2)-NonconcaveExample (i+1) ≤
      NonconcaveExample (i+1)-NonconcaveExample i) := by
  intro h
  have hh := h 1 (by omega)
  norm_num [NonconcaveExample] at hh

#print axioms concavity_implies_increment_admissible
#print axioms lower_increment_bounds_of_admissible
#print axioms crossing_bounds_of_admissible
#print axioms endpoint_order_of_admissible
#print axioms anchored_range_bounds_of_admissible
#print axioms normalized_anchor_member
#print axioms normalized_anchor_member_of_concavity
#print axioms normalized_terminal_lower_attainment
#print axioms nonconcave_example_admissible
#print axioms nonconcave_example_endpoints
#print axioms nonconcave_example_fails_concavity
#print axioms anchored_nonnegative
#print axioms selected_family_size
#print axioms projection_certificate
#print axioms anchored_range_bounds
#print axioms anchored_total
#print axioms anchored_upper_attainment
#print axioms anchored_lower_attainment
#print axioms increment_bounds
#print axioms crossing_anchor_bounds
#print axioms lower_increment_bounds
#print axioms bracket_certificate
#print axioms count_row_feasible
#print axioms terminal_row_duplicate
#print axioms decreasing_slopes
#print axioms decreasing_increments
#print axioms count_row_attains_upper
#print axioms count_row_attains_lower
#print axioms endpoint_order
end MIC5090
