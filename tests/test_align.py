import argparse
import functools
import os

import pytest
import pathlib

from shlex import quote

from Bio import SeqIO
from Bio.Align import MultipleSeqAlignment
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from augur import align


def write_strains(tmpdir, name, strains):
    path = str(tmpdir / name + ".fasta")
    with open(path, "w") as fh:
        SeqIO.write(strains, fh, "fasta")
    return path

@pytest.fixture
def ref_seq():
    return SeqRecord(Seq("aaaaTT-Tg-ggCCCC"), "REF")

@pytest.fixture
def test_seqs(ref_seq):
    return {
        "PREFIX": SeqRecord(ref_seq.seq[3:], "PREFIX"),
        "SUFFIX": SeqRecord(ref_seq.seq[:-3], "SUFFIX"),
        "LONGER": SeqRecord("CCC" + ref_seq.seq + "AAA", "LONGER")
    }

@pytest.fixture
def existing_aln(ref_seq):
    return {
        "EXISTING1": SeqRecord("NN" + ref_seq.seq[2:-3] + "NNN", "EXISTING1"),
        "EXISTING2": SeqRecord("NNN" + ref_seq.seq[3:-1] + "N", "EXISTING2")
    }

@pytest.fixture
def ref_file(tmpdir, ref_seq):
    return write_strains(tmpdir, "ref", ref_seq)

@pytest.fixture
def test_file(tmpdir, test_seqs):
    return write_strains(tmpdir, "test", test_seqs.values())

@pytest.fixture
def test_with_ref(tmpdir, test_seqs, ref_seq):
    return write_strains(tmpdir, "test_w_ref", [ref_seq,] + list(test_seqs.values()))

@pytest.fixture
def existing_file(tmpdir, existing_aln):
    return write_strains(tmpdir, "existing", existing_aln.values())

@pytest.fixture
def existing_with_ref(tmpdir, existing_aln, ref_seq):
    return write_strains(tmpdir, "existing_w_ref", [ref_seq,] + list(existing_aln.values()))

@pytest.fixture
def out_file(tmpdir):
    out_file = str(tmpdir / "out")
    open(out_file, "w").close()
    return out_file

class TestAlign:
    def test_make_gaps_ambiguous(self):
        alignment = MultipleSeqAlignment(
            [SeqRecord(Seq("G-AC")), SeqRecord(Seq("----")), SeqRecord(Seq("TAGC"))]
        )

        align.make_gaps_ambiguous(alignment)

        assert [seq_record.seq for seq_record in alignment] == [
            Seq("GNAC"),
            Seq("NNNN"),
            Seq("TAGC"),
        ]

    def test_check_duplicates_no_arguments(self):
        assert align.check_duplicates() is None

    def test_check_duplicates_strings_with_no_duplicates(self):
        assert align.check_duplicates("GTAC", "CGTT") is None

    def test_check_duplicates_MSA_with_no_duplicates(self):
        alignment = MultipleSeqAlignment(
            [
                SeqRecord(Seq("GTAC"), name="seq1"),
                SeqRecord(Seq("CGTT"), name="seq2"),
                SeqRecord(Seq("TAGC"), name="seq3"),
            ]
        )
        assert align.check_duplicates(alignment) is None

    def test_check_duplicates_MSA_and_string_with_no_duplicates(self):
        alignment = MultipleSeqAlignment(
            [
                SeqRecord(Seq("GTAC"), name="seq1"),
                SeqRecord(Seq("CGTT"), name="seq2"),
                SeqRecord(Seq("TAGC"), name="seq3"),
            ]
        )
        assert align.check_duplicates(alignment, "TGTT") is None

    def test_check_duplicates_string_with_duplicates(self):
        with pytest.raises(align.AlignmentError):
            assert align.check_duplicates("GTAC", "CGTT", "CGTT")

    def test_check_duplicates_MSA_with_duplicates(self):
        alignment = MultipleSeqAlignment(
            [
                SeqRecord(Seq("GTAC"), name="seq1"),
                SeqRecord(Seq("CGTT"), name="seq2"),
                SeqRecord(Seq("TAGC"), name="seq3"),
                SeqRecord(Seq("TAGC"), name="seq3"),
            ]
        )
        with pytest.raises(align.AlignmentError):
            assert align.check_duplicates(alignment)

    def test_check_duplicates_MSA_and_string_with_duplicates(self):
        alignment = MultipleSeqAlignment(
            [
                SeqRecord(Seq("GTAC"), name="seq1"),
                SeqRecord(Seq("CGTT"), name="seq2"),
                SeqRecord(Seq("TAGC"), name="seq3"),
            ]
        )
        with pytest.raises(align.AlignmentError):
            assert align.check_duplicates(alignment, "seq3")

    def test_prune_seqs_matching_alignment(self):
        sequence = {
            "seq1": SeqRecord(Seq("GTAC"), name="seq1"),
            "seq2": SeqRecord(Seq("CGTT"), name="seq2"),
            "seq3": SeqRecord(Seq("TAGC"), name="seq3"),
        }
        alignment = MultipleSeqAlignment(
            [
                SeqRecord(Seq("GTAC"), name="seq1"),
                SeqRecord(Seq("TAGC"), name="seq3"),
            ]
        )
        
        result = align.prune_seqs_matching_alignment(sequence.values(), alignment)
        assert [r.name for r in result] == ["seq2"]
        for r in result:
            assert r.seq == sequence[r.name].seq

    def test_prettify_alignment(self):
        data_file = pathlib.Path('tests/data/align/test_aligned_sequences.fasta')
        alignment = align.read_alignment(str(data_file.resolve()))
        seqs = {s.id:s for s in alignment}
        assert "_R_crick_strand" in seqs

        align.prettify_alignment(alignment)
        seqs = {s.id:s for s in alignment}
        assert "crick_strand" in seqs

    def test_generate_alignment_cmd_non_mafft(self):
        with pytest.raises(align.AlignmentError):
            assert align.generate_alignment_cmd('no-mafft', 1, None, None, None, None)
            
    def test_generate_alignment_cmd_mafft_existing_aln_fname(self):
        existing_aln_fname = "existing_aln"
        seqs_to_align_fname = "seqs_to_align"
        aln_fname = "aln_fname"
        log_fname = "log_fname"
        
        result = align.generate_alignment_cmd("mafft", 1,
                                              existing_aln_fname,
                                              seqs_to_align_fname,
                                              aln_fname,
                                              log_fname)
        
        expected = "mafft --add %s --keeplength --reorder --anysymbol --nomemsave --adjustdirection --thread %d %s 1> %s 2> %s" % (quote(seqs_to_align_fname), 1, quote(existing_aln_fname), quote(aln_fname), quote(log_fname))
        
        assert result == expected
                                    
    def test_generate_alignment_cmd_mafft_no_existing_aln_fname(self):
        seqs_to_align_fname = "seqs_to_align"
        aln_fname = "aln_fname"
        log_fname = "log_fname"
        
        result = align.generate_alignment_cmd("mafft", 1,
                                              None,
                                              seqs_to_align_fname,
                                              aln_fname,
                                              log_fname)
        
        expected = "mafft --reorder --anysymbol --nomemsave --adjustdirection --thread %d %s 1> %s 2> %s" % (1, quote(seqs_to_align_fname), quote(aln_fname), quote(log_fname))
        
        assert result == expected
        
    def test_read_alignment(self):
        data_file = pathlib.Path('tests/data/align/test_aligned_sequences.fasta')
        result = align.read_alignment(str(data_file.resolve()))
        
        assert len(result) == 4
        
    def test_read_sequences(self):
        data_file = pathlib.Path('tests/data/align/test_aligned_sequences.fasta')
        result = align.read_sequences(data_file)
        assert len(result) == 4

    def test_read_seq_compare(self):
        data_file = pathlib.Path("tests/data/align/aa-seq_h3n2_ha_2y_2HA1_dup.fasta")
        with pytest.raises(align.AlignmentError):
            assert align.read_sequences(data_file)

    def test_prepare_no_alignment_or_ref(self, test_file, test_seqs, out_file):
        _, output, _ = align.prepare([test_file,], None, out_file, None, None)
        assert os.path.isfile(output), "Didn't write sequences where it said"
        for name, seq in SeqIO.to_dict(SeqIO.parse(output, "fasta")).items():
            assert seq.seq == test_seqs[name].seq
    
    def test_prepare_no_alignment_with_named_ref_missing(self, test_file, ref_seq):
        """We're given a ref_name, but it does not exist in the test file"""
        with pytest.raises(align.AlignmentError):
            align.prepare([test_file,], None, "dontcare", ref_seq.id, None)

    def test_prepare_with_alignment_with_named_ref_missing(self, test_with_ref, existing_file, ref_seq):
        """We're given a ref_name and an existing alignment, but the ref doesn't exist in the existing alignment."""
        with pytest.raises(align.AlignmentError):
            align.prepare([test_with_ref,], existing_file, "dontcare", ref_seq.id, None)

    def test_prepare_no_alignment_with_ref_file(self, test_file, test_seqs, ref_file, ref_seq, out_file):
        _, output_fn, ref_name = align.prepare([test_file,], None, out_file, None, ref_file)
        assert ref_name == ref_seq.id, "Didn't return strain name from refrence file"
        assert os.path.isfile(output_fn), "Didn't write sequences where it said"
        output = list(SeqIO.parse(output_fn, "fasta")) # order matters
        assert output[0].id == ref_seq.id, "Reference sequence is not the first sequence in ouput file!"
        output_names = {record.name for record in output}
        assert all(name in output_names for name in test_seqs), "Some test sequences dropped unexpectedly"
        for record in output[1:]:
            assert record.seq == test_seqs[record.id].seq, "Some test sequences changed unexpectedly"
    
    def test_prepare_no_alignment_with_ref_name(self, test_with_ref, test_seqs, ref_seq, out_file):
        _, output_fn, _ = align.prepare([test_with_ref,], None, out_file, ref_seq.id, None)
        assert os.path.isfile(output_fn), "Didn't write sequences where it said"
        output = SeqIO.to_dict(SeqIO.parse(output_fn, "fasta"))
        assert output[ref_seq.id].seq == ref_seq.seq, "Reference sequence was not added to test sequences"
        for seq in test_seqs:
            assert seq in output, "Some test sequences dropped unexpectedly"
            assert output[seq].seq == test_seqs[seq].seq, "Some test sequences changed unexpectedly"

    def test_prepare_with_alignment_with_ref_name(self, test_file, test_seqs, existing_with_ref, existing_aln, ref_seq, out_file):
        """Test that, given a set of test sequences, an existing alignment, and a reference sequence name, no changes are made."""
        aln_outfile, seqs_outfile, _ = align.prepare([test_file,], existing_with_ref, out_file, ref_seq.id, None)
        assert os.path.isfile(aln_outfile), "Didn't write existing alignment where it said"
        assert aln_outfile == existing_with_ref, "Rewrote the alignment file unexpectedly"
        # Alignment file should be unchanged
        aln_output = SeqIO.to_dict(SeqIO.parse(aln_outfile, "fasta"))
        assert aln_output[ref_seq.id].seq == ref_seq.seq, "Reference sequence dropped from alignment"
        for seq in existing_aln:
            assert seq in aln_output, "Some existing alignment sequences dropped unexpectedly"
            assert aln_output[seq].seq == existing_aln[seq].seq, "Some existing alignment sequences changed unexpectedly"
        # test sequences should be unchanged
        assert os.path.isfile(seqs_outfile), "Didn't write test sequences where it said"
        seq_output = SeqIO.to_dict(SeqIO.parse(seqs_outfile, "fasta"))
        for seq in test_seqs:
            assert seq in seq_output, "Some test sequences unexpectedly dropped"
            assert seq_output[seq].seq == test_seqs[seq].seq, "Some test sequences changed unexpectedly"
        assert seq_output.keys() == test_seqs.keys()

    def test_prepare_with_alignment_with_ref_seq(self, test_file, test_seqs, existing_file, existing_aln, ref_seq, ref_file, out_file):
        """Test that, given a set of test sequences, an existing alignment, and a reference sequence, the reference
        is added to the existing alignment and no other changes are made."""
        aln_outfile, seqs_outfile, ref_name = align.prepare([test_file,], existing_file, out_file, None, ref_file)
        assert ref_name == ref_seq.id, "Didn't return strain name from refrence file"
        assert os.path.isfile(aln_outfile), "Didn't write existing alignment where it said"
        assert aln_outfile != existing_aln, "Unexpectedly overwrote existing alignment"
        # Alignment file should have the reference added
        aln_output = SeqIO.to_dict(SeqIO.parse(aln_outfile, "fasta"))
        assert aln_output[ref_seq.id].seq == ref_seq.seq, "Reference sequence not added to alignment"
        for seq in existing_aln:
            assert seq in aln_output, "Some existing alignment sequences dropped unexpectedly"
            assert aln_output[seq].seq == existing_aln[seq].seq, "Some existing alignment sequences changed unexpectedly"
        # test sequences should be unchanged
        assert os.path.isfile(seqs_outfile), "Didn't write test sequences where it said"
        seq_output = SeqIO.to_dict(SeqIO.parse(seqs_outfile, "fasta"))
        for seq in test_seqs:
            assert seq in seq_output, "Some test sequences unexpectedly dropped"
            assert seq_output[seq].seq == test_seqs[seq].seq, "Some test sequences changed unexpectedly"
        assert seq_output.keys() == test_seqs.keys()
    
    def test_prepare_no_alignment_multiple_test_seqs(self, test_file, test_seqs, ref_file, ref_seq, out_file):
        """Test that we can pass multiple sequence files to prepare() and get one unified file back"""
        # bit of a kludge, but gets us the reference strain in the input files
        _, seq_outfile, _ = align.prepare([test_file, ref_file], None, out_file, ref_seq.id, None)
        seq_output = SeqIO.to_dict(SeqIO.parse(seq_outfile, "fasta"))
        assert seq_output.keys() == set(test_seqs.keys()) | {ref_seq.id}, "Did not combine the two files"
        assert seq_output[ref_seq.id].seq == ref_seq.seq, "Missing sequence from second file"
        for seq in test_seqs:
            assert seq in seq_output, "Some test sequences unexpectedly dropped"
            assert seq_output[seq].seq == test_seqs[seq].seq, "Some test sequences changed unexpectedly"
    
    def test_prepare_with_alignment_with_duplicate_sequences(self, test_file, test_seqs, existing_file, existing_aln, out_file):
        """Test that sequences matching the alignment are removed from the input sequences"""
        _, seq_outfile, _ = align.prepare([existing_file, test_file], existing_file, out_file, None, None)
        seq_output = SeqIO.to_dict(SeqIO.parse(seq_outfile, "fasta"))
        assert seq_output.keys() == test_seqs.keys(), "Did not strip duplicate sequences from test input!"
    
    def test_prepare_with_alignment_ref_sequence_wrong_length(self, test_file, existing_file, ref_seq, ref_file):
        """Test that including a reference sequence with a length different than the existing alignment fails."""
        ref_seq.seq = ref_seq.seq[:-3]
        with open(ref_file, "w") as fh:
            SeqIO.write(ref_seq, fh, "fasta")
        with pytest.raises(align.AlignmentError):
            align.prepare([test_file,], existing_file, "out", None, ref_file)
    
    def test_postprocess_prettify_alignment(self, tmpdir, existing_aln, ref_seq):
        """Postprocess should strip _R_ from reverse-complemented strains and convert all sites to uppercase"""
        ref_seq.name = "_R_" + ref_seq.name
        post_align = write_strains(tmpdir, "post_align", [ref_seq] + list(existing_aln.values()))
        align.postprocess(post_align, None, True, False)
        output = SeqIO.to_dict(SeqIO.parse(post_align, "fasta"))
        for name, record in output.items():
            assert record.seq == record.seq.upper(), "Sequence was not made uppercase"
            assert "_R_" not in name, "Reverse-complement prefix not removed"

    @pytest.mark.parametrize("keep_ref", [True, False])
    def test_postprocess_remove_reference(self, existing_with_ref, ref_seq, keep_ref):
        """Postprocess should remove the reference strain only if requested"""
        align.postprocess(existing_with_ref, ref_seq.id, keep_ref, False)
        output = SeqIO.to_dict(SeqIO.parse(existing_with_ref, "fasta"))
        assert (ref_seq.id in output) == keep_ref
    
    @pytest.mark.parametrize("fill_gaps", [True, False])
    def test_postprocess_fill_gaps(self, existing_file, existing_aln, ref_seq, fill_gaps):
        """Postprocess should make the gaps ambiguous only if requested"""
        align.postprocess(existing_file, None, True, fill_gaps)
        output = SeqIO.to_dict(SeqIO.parse(existing_file, "fasta"))
        for name, record in output.items():
            for idx, site in enumerate(existing_aln[name].seq):
                if site == "-":
                    assert (record.seq[idx] == "N") == fill_gaps

    def test_postprocess_strip_non_reference(self, tmpdir, ref_seq, ref_file):
        """Postprocess should strip gaps in the reference sequence from other sequences, but not gaps in those sequences"""
        expected_length = len(ref_seq.seq) - ref_seq.seq.count("-")
        gapped_seq = ref_seq.seq.tomutable()
        gapped_seq[1] = "-"
        gapped = SeqRecord(gapped_seq, "GAP")
        gap_file = write_strains(tmpdir, "gaps", [ref_seq, gapped])
        align.postprocess(gap_file, ref_seq.id, True, False)
        output = SeqIO.to_dict(SeqIO.parse(gap_file, "fasta"))
        print(output)
        assert "-" not in output[ref_seq.id].seq
        assert output["GAP"].seq.count("-") == 1
        for record in output.values():
            assert len(record.seq) == expected_length