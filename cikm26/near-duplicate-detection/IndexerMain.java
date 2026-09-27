// Minimal Lucene indexer used to build an index that CopyCat's built-in
// AnseriniIndex document resolver can read.
//
// We can NOT use Anserini's own `io.anserini.index.IndexCollection` for this:
// the copycat-cli fat jar bundles two incompatible copies of Lucene side by
// side (Anserini's own, unshaded, old Lucene 7.x, and a newer Lucene 8.x that
// was relocated to the `shaded.org.apache.lucene` package for CopyCat's own
// code). An index written by Anserini's `IndexCollection` uses the unshaded
// Lucene 7.x codec and can not be opened by CopyCat's `AnseriniIndexDocumentResolver`,
// which reads indexes with the shaded Lucene 8.x classes.
//
// This class therefore builds the index directly with the shaded Lucene 8.x
// classes bundled in the copycat-cli jar, storing the fields CopyCat's
// AnseriniIndexDocumentResolver expects: "id" (used to look up a document by
// id) and "contents" (the document's text, read directly since the field is
// stored).
import java.io.BufferedReader;
import java.io.FileReader;
import java.nio.file.Paths;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import shaded.org.apache.lucene.analysis.standard.StandardAnalyzer;
import shaded.org.apache.lucene.document.Document;
import shaded.org.apache.lucene.document.Field;
import shaded.org.apache.lucene.document.StringField;
import shaded.org.apache.lucene.document.TextField;
import shaded.org.apache.lucene.index.IndexWriter;
import shaded.org.apache.lucene.index.IndexWriterConfig;
import shaded.org.apache.lucene.store.FSDirectory;

public class IndexerMain {
    public static void main(String[] args) throws Exception {
        String inputJsonl = args[0];
        String indexDir = args[1];

        FSDirectory dir = FSDirectory.open(Paths.get(indexDir));
        IndexWriterConfig config = new IndexWriterConfig(new StandardAnalyzer());
        IndexWriter writer = new IndexWriter(dir, config);
        ObjectMapper mapper = new ObjectMapper();

        int count = 0;
        try (BufferedReader reader = new BufferedReader(new FileReader(inputJsonl))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) {
                    continue;
                }
                JsonNode node = mapper.readTree(line);
                String id = node.get("id").asText();
                String contents = node.get("contents").asText();

                Document doc = new Document();
                doc.add(new StringField("id", id, Field.Store.YES));
                doc.add(new TextField("contents", contents, Field.Store.YES));
                writer.addDocument(doc);
                count++;
            }
        }

        writer.commit();
        writer.close();
        dir.close();
        System.out.println("Indexed " + count + " documents into " + indexDir);
    }
}
