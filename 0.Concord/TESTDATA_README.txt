=========================================================================
TEST DATA -- Education chain + degree-3 rule -- FH_example benchmark v2
Companion file to concord_FH_example_edu_degree3.txt / VARDOM.txt / REGOLE.txt
=========================================================================

Layout (fixed format, 9 characters per record):

  ENROLL(1)  EDULEV(1)  DEGREE(1)  DEGLEV(1)  DEGCTY(1)  FIELD(2)  AGE(2)

All expected costs/solutions below were computed by this project's own
Fellegi-Holt resolution engine (generate_implied_edits.py + exhaustive
minimum-hitting-set search over the closure), NOT derived by hand.
Field weights: ENROLL=4, EDULEV=3, DEGREE=2, DEGLEV=1, DEGCTY=1, FIELD=1,
AGE=5.

-------------------------------------------------------------------------
The three new rules
-------------------------------------------------------------------------
A: AGE(00-14) EDULEV(8,9)        -- a minor should not show a
                                     higher-education EDULEV code
B: AGE(00-14) DEGLEV(1-8)        -- a minor should not have any
                                     degree level recorded
C: DEGCTY(1) FIELD(5) DEGLEV(4)  -- degree-3, genuinely irreducible:
   field-of-specialisation 5 exists only at technical-diploma level in
   the FH_example education system; the same field+level combination is plausible
   if the degree was obtained abroad (DEGCTY=2). No pair of these three
   conditions alone justifies flagging an error -- only the joint triple.

-------------------------------------------------------------------------
IMPORTANT: a verified interaction, kept deliberately (not a bug)
-------------------------------------------------------------------------
Rule B combines with the pre-existing V3_nonblank rule (DEGREE!=2 ->
DEGLEV must be filled) to imply: "AGE<15 -> DEGREE must equal 2 exactly
(not blank, not 1)". Reasoning: if DEGREE were blank or 1, V3_nonblank
would require DEGLEV filled -- but rule B forbids DEGLEV filled under
15. The only way out is DEGREE=2 explicitly.

This means a legitimately never-enrolled child (ENROLL=4, DEGREE
correctly blank per V2) now costs more to make fully consistent than in
the simpler 6-variable version of this example, because the previously
cheap fix (fill DEGCTY/DEGLEV/FIELD directly, leaving DEGREE blank) is
no longer valid for a record with AGE<15. Confirmed logically consistent
(no contradiction) with the project's resolution engine; the decision to
keep rule B exactly as stated, accepting this consequence, was made
deliberately.

-------------------------------------------------------------------------
Record-by-record (expected minimum-cost correction)
-------------------------------------------------------------------------
R1  "181410645"  valid, no correction needed.
R2  "4      08"  ENROLL=4, all else blank, AGE=8.
    Expected: {DEGREE, EDULEV, ENROLL}, cost 9 (see interaction note above).
R3  "162    25"  valid, no correction needed.
R4  "45     40"  violates V1.
    Expected: {DEGREE, ENROLL}, cost 6.
R5  "1723   30"  violates V3.
    Expected: {DEGLEV}, cost 1.
R6  "432110350" violates all 5 pairwise rules.
    Expected: {DEGREE, EDULEV}, cost 5.
R7  "2 1220922" violates V1 (non-blank form).
    Expected: {EDULEV}, cost 3.
R8  "192    10" AGE=10, EDULEV=9 -- isolates rule A.
    Expected: {EDULEV}, cost 3.
R9  "161320711" AGE=11, DEGLEV=3 -- isolates rule B.
    Expected: {AGE}, cost 5.
R10 "181410530" DEGCTY=1, FIELD=5, DEGLEV=4, AGE=30 -- isolates rule C.
    Expected: {DEGCTY} or {DEGLEV} or {FIELD} (3-way tie), cost 1.
R11 "492410509" maximal stress test: all 5 pairwise + A + B + C.
    Expected: cost 11, three tied solutions of 4 variables each:
    {AGE,DEGCTY,DEGREE,EDULEV} / {AGE,DEGLEV,DEGREE,EDULEV} /
    {AGE,DEGREE,EDULEV,FIELD}.

-------------------------------------------------------------------------
Why these reference answers matter
-------------------------------------------------------------------------
Compare real results from CONCORD/SCIA, IBM, D-Wave, and Dirac-3 against
these expected values AND against each other, the same way the original
6-variable example was cross-checked against LISTAIMP.FH_example.
Records R10 and R11 in particular test whether each solver's
QUBO/Hamiltonian construction correctly handles the genuine degree-3
term (rule C) without needing quadratization (IBM, Dirac-3) or with
correct auxiliary-variable quadratization (D-Wave, via dimod.make_quadratic
or an equivalent -- not yet wired into dwave_solver.py, see prior
discussion on this thread).
