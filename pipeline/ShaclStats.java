// Validate one data graph against several shapes graphs with Jena SHACL and
// write aggregated statistics (not the full report, which can have millions of
// entries on a large KG). The data graph is loaded once, and validation runs
// one focus node at a time so that memory does not grow with the number of
// violations (a whole-graph report ran out of an 8 GB heap on CCKG).
//
// Validation of some shapes graphs is very slow on large KGs (e.g. chains of
// sh:node references re-validate neighbouring nodes over and over). Focus nodes
// are therefore visited in a shuffled order (fixed seed) and, once the time
// budget VALIDATION_BUDGET (seconds, default 3600) is spent, the statistics are
// reported for the random sample validated so far, with "partial": true.
//
// usage: java -cp <jena classpath> ShaclStats.java DATA [--focus-paths] OUT1.json SHAPES1.ttl [OUT2.json SHAPES2.ttl ...]
//
// Each OUT.json holds {conforms, violations, focus_nodes, by_component,
// top_path_components (the 40 most frequent "path component" pairs)} or {error};
// with --focus-paths it also lists the distinct [focus node, result path] pairs.
import java.io.FileWriter;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;
import java.util.stream.Collectors;

import org.apache.jena.graph.Graph;
import org.apache.jena.graph.Node;
import org.apache.jena.riot.RDFDataMgr;
import org.apache.jena.shacl.ShaclValidator;
import org.apache.jena.shacl.Shapes;
import org.apache.jena.shacl.ValidationReport;
import org.apache.jena.shacl.parser.Shape;
import org.apache.jena.shacl.validation.ReportEntry;
import org.apache.jena.shacl.validation.VLib;

public class ShaclStats {
    public static void main(String[] args) throws Exception {
        Graph data = RDFDataMgr.loadGraph(args[0]);
        int i = 1;
        boolean focusPaths = args[i].equals("--focus-paths");
        if (focusPaths) i++;
        for (; i + 1 < args.length; i += 2) {
            try (Writer out = new FileWriter(args[i])) {
                out.write(validate(data, args[i + 1], focusPaths));
            }
        }
    }

    static String validate(Graph data, String shapesFile, boolean focusPaths) {
        try {
            Shapes shapes = Shapes.parse(RDFDataMgr.loadGraph(shapesFile));
            Set<Node> targetSet = new LinkedHashSet<>();
            for (Shape shape : shapes.getTargetShapes())
                targetSet.addAll(VLib.focusNodes(data, shape));
            List<Node> targets = new ArrayList<>(targetSet);
            Collections.shuffle(targets, new Random(42));
            long budgetMillis = 1000L * Long.parseLong(System.getenv().getOrDefault("VALIDATION_BUDGET", "3600"));
            long start = System.currentTimeMillis();
            Map<String, Integer> byComponent = new HashMap<>();
            Map<String, Integer> byPathComponent = new HashMap<>();
            Set<Node> focus = new HashSet<>();
            Set<List<String>> pairs = new HashSet<>();
            long n = 0;
            int validated = 0;
            for (Node target : targets) {
                if (System.currentTimeMillis() - start > budgetMillis)
                    break;
                if (++validated % 10000 == 0)
                    System.err.printf("%s: %d/%d focus nodes, %d violations, %ds%n", shapesFile, validated,
                            targets.size(), n, (System.currentTimeMillis() - start) / 1000);
                // validates the node against every shape that targets it
                ValidationReport report = ShaclValidator.get().validate(shapes, data, target);
                for (ReportEntry e : report.getEntries()) {
                    n++;
                    focus.add(e.focusNode());
                    String component = shorten(e.sourceConstraintComponent().getURI());
                    byComponent.merge(component, 1, Integer::sum);
                    byPathComponent.merge((e.resultPath() == null ? "(node)" : e.resultPath().toString()) + " " + component,
                            1, Integer::sum);
                    if (focusPaths)
                        pairs.add(List.of(str(e.focusNode()), e.resultPath() == null ? "None" : e.resultPath().toString()));
                }
            }
            StringBuilder sb = new StringBuilder("{\"conforms\": " + (n == 0)
                    + ", \"violations\": " + n + ", \"focus_nodes\": " + focus.size()
                    + ", \"validated_focus_nodes\": " + validated + ", \"target_focus_nodes\": " + targets.size()
                    + ", \"partial\": " + (validated < targets.size())
                    + ", \"seconds\": " + (System.currentTimeMillis() - start) / 1000 + ", \"by_component\": {");
            sb.append(byComponent.entrySet().stream()
                    .sorted((a, b) -> b.getValue() - a.getValue())
                    .map(x -> json(x.getKey()) + ": " + x.getValue()).collect(Collectors.joining(", ")));
            sb.append("}, \"top_path_components\": {");
            sb.append(byPathComponent.entrySet().stream()
                    .sorted((a, b) -> b.getValue() - a.getValue()).limit(40)
                    .map(x -> json(x.getKey()) + ": " + x.getValue()).collect(Collectors.joining(", ")));
            sb.append("}");
            if (focusPaths) {
                List<String> items = new ArrayList<>();
                for (List<String> p : pairs) items.add("[" + json(p.get(0)) + ", " + json(p.get(1)) + "]");
                sb.append(", \"focus_paths\": [").append(String.join(", ", items)).append("]");
            }
            return sb.append("}\n").toString();
        } catch (Throwable t) {
            return "{\"error\": " + json(t.getClass().getSimpleName() + ": " + t.getMessage()) + "}\n";
        }
    }

    static String shorten(String uri) {
        return uri.replace("http://www.w3.org/ns/shacl#", "sh:");
    }

    static String str(Node n) {
        return n.isURI() ? n.getURI() : n.toString();
    }

    static String json(String s) {
        if (s == null) s = "null";
        StringBuilder sb = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"' || c == '\\') sb.append('\\').append(c);
            else if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
            else sb.append(c);
        }
        return sb.append('"').toString();
    }
}
