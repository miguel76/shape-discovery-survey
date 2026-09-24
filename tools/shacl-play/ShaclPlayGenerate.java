// Minimal launcher equivalent to SHACL Play's `generate` CLI command
// (shacl-play-app/.../app/generate/Generate.java), built only on the
// shacl-generate module so we don't need shacl-play-app's jitpack-only
// dependencies. Run with Java's single-file source launcher:
//   java -cp <shacl-generate classpath> ShaclPlayGenerate.java (file|endpoint) SOURCE OUTPUT.ttl
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.Map;

import org.apache.jena.rdf.model.Model;
import org.apache.jena.rdf.model.ModelFactory;
import org.apache.jena.riot.RDFDataMgr;

import fr.sparna.rdf.shacl.generate.Configuration;
import fr.sparna.rdf.shacl.generate.DefaultModelProcessor;
import fr.sparna.rdf.shacl.generate.PaginatedQuery;
import fr.sparna.rdf.shacl.generate.ShaclGenerator;
import fr.sparna.rdf.shacl.generate.providers.SamplingShaclGeneratorDataProvider;
import fr.sparna.rdf.shacl.generate.providers.ShaclGeneratorDataProviderIfc;
import fr.sparna.rdf.shacl.generate.visitors.AssignDatatypesAndClassesToIriOrLiteralVisitor;
import fr.sparna.rdf.shacl.generate.visitors.AssignLabelRoleVisitor;

public class ShaclPlayGenerate {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println("usage: ShaclPlayGenerate (file|endpoint) SOURCE OUTPUT.ttl");
            System.exit(2);
        }
        Configuration config = new Configuration(new DefaultModelProcessor(), "https://shacl-play.sparna.fr/shapes/", "shape");
        config.setShapesOntology("https://shacl-play.sparna.fr/shapes/");

        Model inputModel = null;
        ShaclGeneratorDataProviderIfc dataProvider;
        if (args[0].equals("endpoint")) {
            dataProvider = new SamplingShaclGeneratorDataProvider(new PaginatedQuery(100), args[1]);
        } else {
            inputModel = ModelFactory.createDefaultModel();
            RDFDataMgr.read(inputModel, args[1]);
            dataProvider = new SamplingShaclGeneratorDataProvider(new PaginatedQuery(100), inputModel);
        }
        ShaclGenerator generator = new ShaclGenerator();
        generator.getExtraVisitors().add(new AssignLabelRoleVisitor());
        generator.getExtraVisitors().add(new AssignDatatypesAndClassesToIriOrLiteralVisitor(dataProvider, new DefaultModelProcessor()));
        Model shapes = generator.generateShapes(config, dataProvider);

        if (inputModel != null) {
            for (Map.Entry<String, String> m : inputModel.getNsPrefixMap().entrySet()) {
                if (shapes.getNsPrefixURI(m.getKey()) == null) shapes.setNsPrefix(m.getKey(), m.getValue());
            }
        }
        try (OutputStream out = new FileOutputStream(args[2])) {
            shapes.write(out, "Turtle");
        }
    }
}
