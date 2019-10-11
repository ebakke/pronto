import abc
import io
import os
import operator
import typing
from typing import BinaryIO, ClassVar

import fastobo

from ..metadata import Metadata
from ..ontology import Ontology
from ..synonym import SynonymData
from ..term import Term, TermData
from ..relationship import RelationshipData
from ..xref import Xref
from ..pv import PropertyValue, LiteralPropertyValue, ResourcePropertyValue


class FastoboSerializer:

    def _to_obodoc(self, o: Ontology) -> fastobo.doc.OboDoc:
        doc = fastobo.doc.OboDoc()
        if o.metadata:
            doc.header = self._to_header_frame(o.metadata)
        for termdata in sorted(self.ont._terms.values(), key=operator.attrgetter("id")):
            doc.append(self._to_term_frame(termdata))
        for reldata in sorted(self.ont._relationships.values(), key=operator.attrgetter("id")):
            doc.append(self._to_typedef_frame(reldata))
        return doc

    def _to_header_frame(self, m: Metadata) -> fastobo.header.HeaderFrame:
        # Ordering of tags follow the OBO 1.4 specification
        frame = fastobo.header.HeaderFrame()
        if m.format_version is not None:
            frame.append(fastobo.header.FormatVersionClause(m.format_version))
        if m.data_version is not None:
            frame.append(fastobo.header.DataVersionClause(m.data_version))
        if m.date is not None:
            frame.append(fastobo.header.DateClause(m.date))
        if m.saved_by is not None:
            frame.append(fastobo.header.SavedByClause(m.saved_by))
        if m.auto_generated_by is not None:
            frame.append(fastobo.header.AutoGeneratedByClause(m.auto_generated_by))
        for i in sorted(m.imports):
            frame.append(fastobo.header.ImportClause(i))
        for subset in sorted(m.subsetdefs):
            frame.append(fastobo.header.SubsetdefClause(
                subset=fastobo.id.parse(subset.name),
                description=subset.description
            ))
        for syn in sorted(m.synonymtypedefs):
            frame.append(fastobo.header.SynonymTypedefClause(
                typedef=fastobo.id.parse(syn.id),
                description=syn.description,
                scope=syn.scope,
            ))
        if m.default_namespace is not None:
            frame.append(fastobo.header.DefaultNamespaceClause(
                m.default_namespace
            ))
        if m.namespace_id_rule is not None:
            frame.append(fastobo.header.NamespaceIdRuleClause(m.namespace_id_rule))
        for id, (url, description) in sorted(m.idspaces.items()):
            frame.append(fastobo.header.IdspaceClause(id, url, description))
        for pv in sorted(m.annotations):
            frame.append(fastobo.header.PropertyValueClause(self._to_property_value(pv)))
        for remark in sorted(m.remarks):
            frame.append(fastobo.header.RemarkClause(remark))
        if m.ontology is not None:
            frame.append(fastobo.header.OntologyClause(m.ontology))
        for line in m.owl_axioms:
            frame.append(fastobo.header.OwlAxiomsClause(line))
        for tag, values in sorted(m.unreserved.items()):
            for value in values:
                frame.append(fastobo.header.UnreservedClause(tag, value))
        return frame

    def _to_property_value(self, pv: PropertyValue) -> fastobo.pv.AbstractPropertyValue:
        try:
            return fastobo.pv.ResourcePropertyValue(
                fastobo.id.parse(pv.property),
                fastobo.id.parse(pv.resource),
            )
        except AttributeError:
            return fastobo.pv.LiteralPropertyValue(
                fastobo.id.parse(pv.property),
                pv.literal,
                fastobo.id.parse(pv.datatype)
            )

    def _to_synonym(self, syn: SynonymData) -> fastobo.syn.Synonym:
        return fastobo.syn.Synonym(
            syn.description,
            syn.scope,
            None if syn.type is None else fastobo.id.parse(syn.type),
            map(self._to_xref, syn.xrefs),
        )

    def _to_term_frame(self, t: TermData) -> fastobo.term.TermFrame:
        frame = fastobo.term.TermFrame(fastobo.id.parse(t.id))
        if t.anonymous:
            frame.append(fastobo.term.IsAnonymousClause(True))
        if t.name is not None:
            frame.append(fastobo.term.NameClause(t.name))
        if t.namespace is not None:
            if t.namespace != self.ont.default_namespace:
                frame.append(fastobo.term.NamespaceClause(t.namespace))
        for alt in sorted(t.alternate_ids):
            frame.append(fastobo.term.AltIdClause(fastobo.id.parse(alt)))
        if t.definition is not None:
            frame.append(fastobo.term.DefClause(
                str(t.definition),
                [self._to_xref(x) for x in sorted(t.definition.xrefs)],
            ))
        if t.comment is not None:
            frame.append(fastobo.term.CommentClause(t.comment))
        for subset in sorted(t.subsets):
            frame.append(fastobo.term.SubsetClause(fastobo.id.parse(subset)))
        for syn in sorted(t.synonyms):
            frame.append(fastobo.term.SynonymClause(self._to_synonym(syn)))
        for xref in sorted(t.xrefs):
            frame.append(fastobo.term.XrefClause(self._to_xref(xref)))
        if t.builtin:
            frame.append(fastobo.term.BuiltinClause(True))
        for pv in sorted(t.annotations):
            frame.append(fastobo.term.PropertyValueClause(self._to_property_value(pv)))
        for superclass in sorted(t.relationships.get('is_a', ())):
            frame.append(fastobo.term.IsAClause(fastobo.id.parse(superclass)))
        for i in sorted(filter( lambda x: len(x) == 1, t.intersection_of)):
            frame.append(fastobo.term.IntersectionOfClause(
                term=fastobo.id.parse(i)
            ))
        for (i, j) in sorted(filter( lambda x: len(x) == 2, t.intersection_of)):
            frame.append(fastobo.term.IntersectionOfClause(
                typedef=fastobo.id.parse(i),
                term=fastobo.id.parse(j)
            ))
        for id_ in sorted(t.union_of):
            frame.append(fastobo.term.UnionOfClause(fastobo.id.parse(id_)))
        for id_ in sorted(t.equivalent_to):
            frame.append(fastobo.term.EquivalentToClause(fastobo.id.parse(id_)))
        for id_ in sorted(t.disjoint_from):
            frame.append(fastobo.term.DisjointFromClause(fastobo.id.parse(id_)))
        for r, values in t.relationships.items():
            if r != "is_a":
                r_id = fastobo.id.parse(r)
                for value in values:
                    t_id = fastobo.id.parse(value)
                    frame.append(fastobo.term.RelationshipClause(r_id, t_id))
        if t.created_by is not None:
            frame.append(fastobo.term.CreatedByClause(t.created_by))
        if t.creation_date is not None:
            frame.append(fastobo.term.CreationDateClause(t.creation_date))
        if t.obsolete:
           frame.append(fastobo.term.IsObsoleteClause(True))
        for r in sorted(t.replaced_by):
            frame.append(fastobo.term.ReplacedByClause(fastobo.id.parse(r)))
        for c in sorted(t.consider):
           frame.append(fastobo.term.ConsiderClause(fastobo.id.parse(c)))
        return frame

    def _to_typedef_frame(self, r: RelationshipData):
        frame = fastobo.typedef.TypedefFrame(fastobo.id.parse(r.id))
        if r.anonymous:
            frame.append(fastobo.typedef.IsAnonymousClause(True))
        if r.name is not None:
            frame.append(fastobo.typedef.NameClause(r.name))
        if r.namespace is not None:
            if r.namespace != self.ont.default_namespace:
                frame.append(fastobo.typedef.NamespaceClause(r.namespace))
        for alt in sorted(r.alternate_ids):
            frame.append(fastobo.typedef.AltIdClause(fastobo.id.parse(alt)))
        if r.definition is not None:
            frame.append(fastobo.typedef.DefClause(
                str(r.definition),
                [self._to_xref(x) for x in sorted(r.definition.xrefs)],
            ))
        if r.comment is not None:
            frame.append(fastobo.typedef.CommentClause(r.comment))
        for subset in sorted(r.subsets):
            frame.append(fastobo.typedef.SubsetClause(fastobo.id.parse(subset)))
        for syn in sorted(r.synonyms):
            frame.append(fastobo.typedef.SynonymClause(self._to_synonym(syn)))
        for xref in sorted(r.xrefs):
            frame.append(fastobo.typedef.XrefClause(self._to_xref(xref)))
        for pv in sorted(r.annotations):
            frame.append(fastobo.typedef.PropertyValueClause(self._to_property_value(pv)))
        if r.domain is not None:
            frame.append(fastobo.typedef.DomainClause(fastobo.id.parse(r.domain)))
        if r.range is not None:
            frame.append(fastobo.typedef.RangeClause(fastobo.id.parse(r.range)))
        if r.builtin:
            frame.append(fastobo.typedef.BuiltinClause(True))
        for chain in sorted(r.holds_over_chain):
            frame.append(fastobo.typedef.HoldsOverChainClause(*chain))
        if r.antisymmetric:
            frame.append(fastobo.typedef.IsAntiSymmetricClause(True))
        if r.cyclic:
            frame.append(fastobo.typedef.IsCyclicClause(True))
        if r.reflexive:
            frame.append(fastobo.typedef.IsReflexiveClause(True))
        if r.asymmetric:
            frame.append(fastobo.typedef.IsAsymmetricClause(True))
        if r.symmetric:
            frame.append(fastobo.typedef.IsSymmetricClause(True))
        if r.transitive:
            frame.append(fastobo.typedef.IsTransitiveClause(True))
        if r.functional:
            frame.append(fastobo.typedef.IsFunctionalClause(True))
        if r.inverse_functional:
            frame.append(fastobo.typedef.IsInverseFunctionalClause(True))
        for superclass in sorted(r.relationships.get('is_a', ())):
            frame.append(fastobo.typedef.IsAClause(fastobo.id.parse(superclass)))
        for i in sorted(r.intersection_of):
            frame.append(fastobo.typedef.IntersectionOfClause(fastobo.id.parse(i)))
        for id_ in sorted(r.union_of):
            frame.append(fastobo.typedef.UnionOfClause(fastobo.id.parse(id_)))
        for id_ in sorted(r.equivalent_to):
            frame.append(fastobo.typedef.EquivalentToClause(fastobo.id.parse(id_)))
        for id_ in sorted(r.disjoint_from):
            frame.append(fastobo.typedef.DisjointFromClause(fastobo.id.parse(id_)))
        if r.inverse_of is not None:
            frame.append(fastobo.typedef.InverseOfClause(fastobo.id.parse(r.inverse_of)))
        for id_ in sorted(r.transitive_over):
            frame.append(fastobo.typedef.TransitiveOverClause(fastobo.id.parse(id_)))
        for chain in sorted(r.equivalent_to_chain):
            c1, c2 = map(fastobo.id.parse, chain)
            frame.append(fastobo.typedef.EquivalentToChainClause(c1, c2))
        for id_ in sorted(r.disjoint_over):
            frame.append(fastobo.typedef.DisjointOverClause(fastobo.id.parse(id_)))
        for rel, values in r.relationships.items():
            if rel != "is_a":
                r_id = fastobo.id.parse(rel)
                for value in values:
                    t_id = fastobo.id.parse(value)
                    frame.append(fastobo.typedef.RelationshipClause(r_id, t_id))
        if r.obsolete:
            frame.append(fastobo.typedef.IsObsoleteClause(True))
        if r.created_by is not None:
            frame.append(fastobo.typedef.CreatedByClause(r.created_by))
        if r.creation_date is not None:
            frame.append(fastobo.typedef.CreationDateClause(r.creation_date))
        for r in sorted(r.replaced_by):
            frame.append(fastobo.typedef.ReplacedByClause(fastobo.id.parse(r)))
        for c in sorted(r.consider):
           frame.append(fastobo.typedef.ConsiderClause(fastobo.id.parse(c)))
        for d in r.expand_assertion_to:
            frame.append(fastobo.typedef.ExpandAssertionToClause(
                str(d),
                [self._to_xref(x) for x in sorted(d.xrefs)],
            ))
        for d in r.expand_expression_to:
            frame.append(fastobo.typedef.ExpandExpressionToClause(
                str(d),
                [self._to_xref(x) for x in sorted(d.xrefs)],
            ))
        if r.metadata_tag:
            frame.append(fastobo.typedef.IsMetadataClause(True))
        if r.class_level:
            frame.append(fastobo.typedef.IsClassLevel(True))
        return frame

    def _to_xref(self, x: Xref) -> fastobo.xref.Xref:
        return fastobo.xref.Xref(fastobo.id.parse(x.id), x.description)
