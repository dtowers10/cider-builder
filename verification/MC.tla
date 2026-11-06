---- MODULE MC ----
EXTENDS JobProtocol, TLC
MCSlots1 == [w \in Workers |-> 1]
MCSlots2 == [w \in Workers |-> 2]
MCSymmetry == Permutations(Keys)
====
